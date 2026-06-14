"""
Core DJ set builder — shared engine used by all brain modules.

Call build_full_set(brain) where brain is any module (or object) that exposes:
  SET_NAME   str      — output folder name under output/
  SET_NOTES  str      — creative text written to SET_NOTES.txt
  TRACKS     list     — list of track dicts: {name, label, path, hint, mix_in_bars}
  CF_BARS    int      — crossfade length in bars (default 8)
  OUTRO_BARS int      — how many bars from end of A to start blend (default 16)
  SNIPPET_SEC int     — half-length of transition clip in seconds (default 6 → 12s total)
"""
import os, sys
import numpy as np
from pydub import AudioSegment

from mixer.beatgrid import get_or_analyze, snap_to_beat
from mixer.transition import (
    _seg_to_f32, _f32_to_seg, _equal_power,
    find_cue_point, _time_stretch_samples, _beat_this_phase_trim,
)

PHASE_THRESHOLD_MS = 20.0


# ── Phase measurement ─────────────────────────────────────────────────────────

def _phase_error_ms(blend_path):
    """Blend-file linear regression — ±1ms accuracy, no PRE/POST startup bias."""
    try:
        from beat_this.inference import File2Beats
        beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(blend_path)
    except Exception:
        return None
    if len(beats) < 6:
        return None
    beats = np.array(beats, dtype=float)
    n = len(beats)
    i = np.arange(n, dtype=float)
    coeffs, _, _, _ = np.linalg.lstsq(
        np.column_stack([np.ones(n), i]), beats, rcond=None
    )
    anchor_fit, period_fit = coeffs
    residuals = beats - (anchor_fit + i * period_fit)
    mid = n // 2
    err = float(np.mean(residuals[mid:])) - float(np.mean(residuals[:mid]))
    while err >  period_fit / 2: err -= period_fit
    while err < -period_fit / 2: err += period_fit
    return round(abs(err) * 1000, 1)


# ── Single transition builder ─────────────────────────────────────────────────

def build_one_transition(track_a, track_b, out_dir, cf_bars, outro_bars):
    """Beat-align A→B, measure phase error, return metrics + audio arrays."""
    grid_a = get_or_analyze(track_a["path"], hint_bpm=track_a["hint"])
    grid_b = get_or_analyze(track_b["path"], hint_bpm=track_b["hint"])

    bpm_a, bpm_b = grid_a["bpm"], grid_b["bpm"]
    diff_pct = abs(bpm_a - bpm_b) / bpm_a * 100
    if diff_pct > 8.0:
        raise ValueError(f"BPM too far: {bpm_a:.1f} vs {bpm_b:.1f} ({diff_pct:.1f}%)")

    seg_a = AudioSegment.from_file(track_a["path"]).set_channels(2)
    seg_b = AudioSegment.from_file(track_b["path"]).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    period_a = float(grid_a["beat_period_samples"])
    period_b = float(grid_b["beat_period_samples"])
    anchor_a = float(grid_a["beat_anchor_sample"])
    anchor_b = float(grid_b["beat_anchor_sample"])

    cue = find_cue_point(seg_b)
    if cue > anchor_b:
        cue = 0
    samples_b  = samples_b[cue:]
    anchor_b  -= cue

    ratio = period_a / period_b
    samples_b_s = _time_stretch_samples(samples_b, sr, ratio) if abs(ratio - 1.0) > 0.0001 else samples_b.copy()
    anchor_b_s  = anchor_b * ratio

    outro_target = len(samples_a) - outro_bars * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    cf_len       = int(round(cf_bars * 4 * period_a))

    mix_in_samples = int(round(track_b.get("mix_in_bars", 16) * 4 * period_a))
    trim = _beat_this_phase_trim(
        samples_a, samples_b_s, sr,
        outro_sample, anchor_b_s + mix_in_samples, period_a, cf_bars,
    )
    trim = max(0, min(trim, len(samples_b_s) - sr))

    # Best of ±1-beat offsets — pick lowest blend beat CV
    best = {"cv": 1e9}
    for offset in range(-1, 3):
        t  = max(0, min(int(round(trim + offset * period_a)), len(samples_b_s) - sr))
        b  = samples_b_s[t:]
        za = samples_a[outro_sample: outro_sample + cf_len]
        zb = b[:cf_len]
        n  = min(len(za), len(zb))
        za, zb = za[:n], zb[:n]
        blend = np.clip(
            za * _equal_power(n, fade_in=False)[:, np.newaxis] +
            zb * _equal_power(n, fade_in=True)[:, np.newaxis],
            -1.0, 1.0,
        )
        tmp = f"/tmp/_sb_cand_{offset}.mp3"
        _f32_to_seg(blend, sr).export(tmp, format="mp3", bitrate="192k")
        try:
            from beat_this.inference import File2Beats
            beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(tmp)
            ibi = np.diff(beats) * 1000
            cv  = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 1 else 1.0
        except Exception:
            cv = 1.0
        if cv < best["cv"]:
            best = {"cv": cv, "blend": blend, "b": b, "n": n, "trim": t}

    os.makedirs(out_dir, exist_ok=True)
    tag        = f"{track_a['name']}_into_{track_b['name']}"
    blend_path = os.path.join(out_dir, f"{tag}_BLEND.mp3")
    _f32_to_seg(best["blend"], sr).export(blend_path, format="mp3", bitrate="192k")

    return {
        "tag":          tag,
        "bpm_a":        bpm_a,
        "bpm_b":        bpm_b,
        "phase_err_ms": _phase_error_ms(blend_path),
        "samples_a":    samples_a,
        "samples_b_s":  samples_b_s,
        "outro_sample": outro_sample,
        "cf_len":       best["n"],
        "blend":        best["blend"],
        "b_full":       best["b"],
        "sr":           sr,
        "period_a":     period_a,
    }


# ── Full mix assembly ─────────────────────────────────────────────────────────

def build_full_set(brain):
    """
    Build a complete DJ set from a brain module.

    brain must expose: SET_NAME, SET_NOTES, TRACKS, CF_BARS, OUTRO_BARS, SNIPPET_SEC
    """
    tracks      = brain.TRACKS
    set_name    = brain.SET_NAME
    set_notes   = brain.SET_NOTES
    cf_bars     = getattr(brain, "CF_BARS",     8)
    outro_bars  = getattr(brain, "OUTRO_BARS",  16)
    snippet_sec = getattr(brain, "SNIPPET_SEC", 6)

    out_dir      = os.path.join("output", set_name)
    blend_dir    = os.path.join("output", "transitions", set_name)
    os.makedirs(out_dir,   exist_ok=True)
    os.makedirs(blend_dir, exist_ok=True)

    print(f"\n{'═'*65}")
    print(f"  Building: {set_name.upper().replace('_',' ')}")
    print(f"  {len(tracks)} tracks  |  CF={cf_bars}bars  OUTRO={outro_bars}bars")
    print(f"{'═'*65}\n")

    grid_0 = get_or_analyze(tracks[0]["path"], hint_bpm=tracks[0]["hint"])
    print(f"  [01] {tracks[0]['label']}  —  {grid_0['bpm']:.2f} BPM")

    # ── Pass 1: build all transitions ─────────────────────────────────────────
    transitions = []
    for i in range(1, len(tracks)):
        prev, curr = tracks[i - 1], tracks[i]
        print(f"\n  [{i+1:02d}] {curr['label']}")
        print(f"       {prev['name']} → {curr['name']}...")

        MIX_IN_ATTEMPTS = [curr.get("mix_in_bars", 16), 8, 0, 24, 32]
        tr, phase_ms = None, None
        for mix_in in MIX_IN_ATTEMPTS:
            tr = build_one_transition(
                prev, dict(curr, mix_in_bars=mix_in),
                blend_dir, cf_bars, outro_bars,
            )
            phase_ms = tr["phase_err_ms"]
            if phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS:
                if mix_in != curr.get("mix_in_bars", 16):
                    print(f"       Retried with mix_in_bars={mix_in}")
                break
            print(f"       mix_in={mix_in}: {phase_ms}ms — retrying...")

        sym = "✓" if (phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS) else "✗"
        print(f"       Phase error: {phase_ms}ms  {sym}")

        if phase_ms is None or phase_ms >= PHASE_THRESHOLD_MS:
            print(f"\n  !! FAIL: {prev['name']}→{curr['name']} phase={phase_ms}ms")
            print(f"     All mix_in attempts exhausted. Aborting.")
            sys.exit(1)

        transitions.append({"tr": tr, "prev": prev, "curr": curr, "phase_ms": phase_ms})

    # ── Pass 2: assemble mix ──────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("  Assembling full mix...")

    mix_audio, mix_len, snippet_clips = None, 0, []
    _, sr = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))

    for idx in range(len(tracks)):
        if idx == 0:
            tr0    = transitions[0]["tr"]
            raw, _ = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))
            body   = raw[:tr0["outro_sample"]]
            mix_audio = body
            mix_len   = len(body)

            blend_start = mix_len
            mix_audio = np.concatenate([mix_audio, tr0["blend"]], axis=0)
            mix_len  += len(tr0["blend"])

            mid = blend_start + len(tr0["blend"]) // 2
            snippet_clips.append({
                "idx": 1,
                "name_a": transitions[0]["prev"]["name"],
                "name_b": transitions[0]["curr"]["name"],
                "start": max(0, mid - snippet_sec * sr),
                "end":   mid + snippet_sec * sr,
            })

        elif idx < len(transitions):
            tr_prev = transitions[idx - 1]["tr"]
            tr_next = transitions[idx]["tr"]
            b_s     = tr_next["samples_b_s"]

            b_body = b_s[tr_prev["cf_len"]: tr_next["outro_sample"]]
            blend_start = mix_len + len(b_body)
            mix_audio = np.concatenate([mix_audio, b_body, tr_next["blend"]], axis=0)
            mix_len  += len(b_body) + len(tr_next["blend"])

            mid = blend_start + len(tr_next["blend"]) // 2
            snippet_clips.append({
                "idx": idx + 1,
                "name_a": transitions[idx]["prev"]["name"],
                "name_b": transitions[idx]["curr"]["name"],
                "start": max(0, mid - snippet_sec * sr),
                "end":   mid + snippet_sec * sr,
            })

        else:
            tr_prev   = transitions[-1]["tr"]
            last_body = tr_prev["samples_b_s"][tr_prev["cf_len"]:]
            mix_audio = np.concatenate([mix_audio, last_body], axis=0)
            mix_len  += len(last_body)

    total_min = len(mix_audio) / sr / 60
    print(f"  Full mix: {total_min:.1f} min")

    full_path = os.path.join(out_dir, "FULL_SET.mp3")
    print(f"  Exporting FULL_SET.mp3...")
    _f32_to_seg(mix_audio, sr).export(full_path, format="mp3", bitrate="256k")
    print(f"  ✓ {full_path}")

    print(f"\n  Exporting transition snippets...")
    for clip in snippet_clips:
        s, e = int(clip["start"]), min(int(clip["end"]), len(mix_audio))
        fname = f"{clip['idx']:02d}_{clip['name_a']}_into_{clip['name_b']}.mp3"
        _f32_to_seg(mix_audio[s:e], sr).export(
            os.path.join(out_dir, fname), format="mp3", bitrate="192k"
        )
        print(f"  ✓ {fname}  ({(e-s)/sr:.1f}s)")

    notes_path = os.path.join(out_dir, "SET_NOTES.txt")
    with open(notes_path, "w") as f:
        f.write(set_notes)
    print(f"\n  ✓ {notes_path}")

    print(f"\n{'═'*65}")
    print(f"  SET COMPLETE: output/{set_name}/")
    print(f"{'═'*65}")
    print(f"  Transitions (threshold < {PHASE_THRESHOLD_MS}ms):")
    for t in transitions:
        sym = "✓" if t["phase_ms"] < PHASE_THRESHOLD_MS else "✗ FAIL"
        print(f"    {t['prev']['name']:<14} → {t['curr']['name']:<14}  {t['phase_ms']}ms  {sym}")
    print()

    return out_dir
