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
import os, sys, math
import numpy as np
from pydub import AudioSegment

from mixer.beatgrid import get_or_analyze, snap_to_beat
from mixer.transition import (
    _seg_to_f32, _f32_to_seg, _equal_power,
    find_cue_point, _time_stretch_samples, _beat_this_phase_trim,
    _mono,
)

PHASE_THRESHOLD_MS = 20.0

# v2: per-band EQ crossfade (Pioneer DJM-800 style).
# True  → bass swaps at 50 % of blend, highs+mids use equal-power.
# False → original uniform equal-power throughout (v1 behaviour).
USE_EQ_BLEND = True


# ── EQ blend helpers ──────────────────────────────────────────────────────────

def _band_split(audio, sr):
    """
    Split stereo [T,2] audio into (bass, mid, high) bands using zero-phase IIR
    filters at 200 Hz and 5 kHz. bass + mid + high == audio exactly.
    """
    from scipy.signal import butter, sosfiltfilt
    nyq = sr / 2.0
    sos_lo = butter(4, 200.0 / nyq, btype='low',  output='sos')
    sos_hi = butter(4, 5000.0 / nyq, btype='high', output='sos')
    bass = sosfiltfilt(sos_lo, audio, axis=0).astype(np.float32)
    high = sosfiltfilt(sos_hi, audio, axis=0).astype(np.float32)
    mid  = (audio - bass - high).astype(np.float32)
    return bass, mid, high


def _eq_blend(za, zb, n, sr):
    """
    DJ-style per-band EQ crossfade.

    High + Mid : standard equal-power crossfade over the full 16-bar blend.
    Bass       : logistic (sigmoid) swap centred at 50 % of blend, ~3.7 s wide
                 at a 31 s blend.  Avoids two sub-bass signals fighting for
                 3–10 seconds and causing comb filtering in the 60–120 Hz range.

    Measurement blends (offset search, drift correction) still use equal-power so
    that beat_this CV and phase scores are clean.  This function is called only
    once, AFTER the best blend position is selected.
    """
    za = za[:n].astype(np.float32)
    zb = zb[:n].astype(np.float32)

    a_bass, a_mid, a_high = _band_split(za, sr)
    b_bass, b_mid, b_high = _band_split(zb, sr)

    p = np.linspace(0.0, 1.0, n, dtype=np.float32)

    ep_out = (np.cos(p * (np.pi / 2.0)) ** 2).reshape(-1, 1)   # A: 1 → 0
    ep_in  = (np.sin(p * (np.pi / 2.0)) ** 2).reshape(-1, 1)   # B: 0 → 1

    w = 0.12   # sigmoid half-width ≈ 12 % of blend ≈ 3.7 s at 31 s blend ≈ 2 bars
    a_bass_g = (1.0 / (1.0 + np.exp((p - 0.5) / w))).reshape(-1, 1)
    b_bass_g = 1.0 - a_bass_g

    blend = (
        a_bass * a_bass_g + b_bass * b_bass_g +
        a_mid  * ep_out   + b_mid  * ep_in    +
        a_high * ep_out   + b_high * ep_in
    )
    return np.clip(blend, -1.0, 1.0)


# BPM ramp defaults — applied to every non-capped body at every body→blend boundary.
# Set RAMP_THRESHOLD = 0.0 so the ramp fires for ALL transitions, including same-nominal-BPM
# pairs whose beat detectors give slightly different period values. Inner guard inside
# _bpm_ramp skips the pyrubberband call when |ratio-1| < 0.0001 (true no-op case).
RAMP_BARS      = 8     # bars to ramp over before the blend (~16s at 122 BPM)
RAMP_CHUNKS    = 32    # kept for API compat; not used in continuous-resample path
RAMP_THRESHOLD = 0.0   # apply ramp to ALL non-capped bodies


# ── BPM ramp helper ──────────────────────────────────────────────────────────

def _bpm_ramp(b_body, sr, target_ratio, body_period,
              ramp_bars=None, ramp_chunks=None):
    """
    Gradually ramp the last ramp_bars bars of b_body from its playing BPM toward the
    blend's native BPM using continuous linear resampling.

    target_ratio = blend_native_period / body_period:
      < 1.0 → compress (speed up body to reach a higher blend BPM)
      > 1.0 → expand  (slow  down body to reach a lower  blend BPM)
      = 1.0 → true no-op (returns b_body unchanged)

    How it works:
      Reads the ramp section at a continuously varying playback rate that linearly
      interpolates from 1.0 (body BPM) to 1/target_ratio (blend BPM). This avoids
      chunk boundaries entirely — no discrete BPM steps, no pyrubberband startup
      artifacts at each boundary.

      For output sample i in [0, n_out):
        advance_rate(i) = 1.0 + (1/target_ratio - 1.0) × i/n_out
        input_pos(i)    = i + (1/target_ratio - 1.0) × i² / (2 × n_out)
        n_out           = int(round(n_in × 2 × target_ratio / (1 + target_ratio)))

      This changes playback speed and pitch simultaneously (like CDJ without keylock).
      The pitch shift is ≤ 0.3 semitones total over the ramp, which is imperceptible.

    ramp_chunks is accepted but ignored (kept for API compatibility with tests).
    Module-level so tests can import and call it with synthetic audio.
    """
    if ramp_bars is None:
        ramp_bars = RAMP_BARS

    ramp_n = int(round(ramp_bars * 4 * body_period))
    if len(b_body) <= ramp_n + int(body_period):
        return b_body  # body too short; skip ramp

    if abs(target_ratio - 1.0) <= 0.0001:
        return b_body  # true no-op

    stable  = b_body[:-ramp_n]
    ramp_in = b_body[-ramp_n:]
    n_in    = len(ramp_in)

    # Output length: integrate advance_rate from 0 to n_out to consume exactly n_in samples.
    # advance_rate goes from 1.0 to inv_r = 1/target_ratio linearly.
    # Integral: n_out + (inv_r - 1) × n_out / 2 = n_in  →  n_out = 2×n_in×r / (1+r)
    inv_r = 1.0 / target_ratio
    n_out = max(1, int(round(n_in * 2.0 * target_ratio / (1.0 + target_ratio))))

    # Input position for each output sample (quadratic accumulation of linear rate)
    i_vec     = np.arange(n_out, dtype=np.float64)
    input_pos = i_vec + (inv_r - 1.0) * i_vec * i_vec / (2.0 * n_out)
    input_pos = np.clip(input_pos, 0.0, n_in - 1.0 - 1e-9)

    # Linear interpolation
    idx0 = input_pos.astype(np.int64)
    idx1 = np.minimum(idx0 + 1, n_in - 1)
    frac = (input_pos - idx0).astype(np.float32)
    if ramp_in.ndim > 1:
        frac = frac[:, np.newaxis]
    ramp_out = (ramp_in[idx0] * (1.0 - frac) + ramp_in[idx1] * frac).astype(np.float32)

    return np.concatenate([stable, ramp_out])


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

    effective_outro_bars = track_a.get("outro_bars", outro_bars)
    outro_target = len(samples_a) - effective_outro_bars * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    cf_len       = int(round(cf_bars * 4 * period_a))

    mix_in_samples = int(round(track_b.get("mix_in_bars", 16) * 4 * period_a))
    trim = _beat_this_phase_trim(
        samples_a, samples_b_s, sr,
        outro_sample, anchor_b_s + mix_in_samples, period_a, cf_bars,
    )
    trim = max(0, min(trim, len(samples_b_s) - sr))

    # Best of ±1-beat offsets — combined score: beat CV + penalty for phase drift.
    # CV alone picks the most rhythmically even blend; phase penalty breaks ties in
    # favour of lower BPM drift so the beats stay locked across the full crossfade.
    def _phase_signed_from_beats(beats_arr):
        """Returns SIGNED phase drift (ms): positive = second half late (B too slow)."""
        beats_arr = np.array(beats_arr, dtype=float)
        if len(beats_arr) < 6:
            return 0.0
        n = len(beats_arr)
        i = np.arange(n, dtype=float)
        coeffs, _, _, _ = np.linalg.lstsq(
            np.column_stack([np.ones(n), i]), beats_arr, rcond=None
        )
        anchor_fit, period_fit = coeffs
        residuals = beats_arr - (anchor_fit + i * period_fit)
        mid = n // 2
        err = float(np.mean(residuals[mid:])) - float(np.mean(residuals[:mid]))
        while err >  period_fit / 2: err -= period_fit
        while err < -period_fit / 2: err += period_fit
        return err * 1000.0

    best = {"score": 1e9, "cv": 1e9, "phase_ms": 999.0, "signed_phase_ms": 0.0}
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
            signed_ms = _phase_signed_from_beats(beats)
            phase_ms  = abs(signed_ms)
        except Exception:
            cv, phase_ms, signed_ms = 1.0, 999.0, 0.0
        # 20ms phase error costs 0.3 CV points — keeps CV dominant but breaks ties
        score = cv + 0.3 * min(phase_ms, 40.0) / 20.0
        print(f"      offset {offset:+d}: CV={cv:.4f} phase={phase_ms:.1f}ms score={score:.4f}")
        if score < best["score"]:
            best = {"score": score, "cv": cv, "phase_ms": phase_ms,
                    "signed_phase_ms": signed_ms,
                    "blend": blend, "b": b, "n": n, "trim": t}

    # ── Ratio drift correction ───────────────────────────────────────────────
    # If the best blend still has residual BPM drift > 3ms, recompute the stretch
    # ratio to cancel it. Cause: beat detector period measurement is accurate to
    # ~0.02-0.1 BPM; a 0.03 BPM mismatch drifts ~7ms over a 31s blend.
    #
    # Math: measured drift D ms over T seconds with n beats means B's effective
    # period is period_a + δ where δ = D/1000 * sr * period_a / cf_len (samples).
    # Corrected ratio: ratio_new = ratio * period_a / (period_a + δ).
    # Trim rescales proportionally since beat positions scale with ratio.
    PHASE_CORR_THRESHOLD_MS = 3.0
    if best["phase_ms"] > PHASE_CORR_THRESHOLD_MS and abs(ratio - 1.0) < 0.10:
        err_s = best["signed_phase_ms"]
        n_beats = best["n"] / period_a
        delta   = (err_s / 1000.0) * sr * period_a / best["n"]  # samples, signed
        ratio_c = ratio * period_a / (period_a + delta)
        if 0.90 < ratio_c < 1.10:  # sanity: stay within ±10%
            b_s_c = (_time_stretch_samples(samples_b, sr, ratio_c)
                     if abs(ratio_c - 1.0) > 0.0001 else samples_b.copy())
            trim_c = max(0, min(int(round(best["trim"] * ratio_c / ratio)),
                                len(b_s_c) - sr))
            za = samples_a[outro_sample: outro_sample + cf_len]
            b_c = b_s_c[trim_c:]
            zb  = b_c[:cf_len]
            n_c = min(len(za), len(zb))
            blend_c = np.clip(
                za[:n_c] * _equal_power(n_c, fade_in=False)[:, np.newaxis] +
                zb[:n_c] * _equal_power(n_c, fade_in=True)[:, np.newaxis],
                -1.0, 1.0,
            )
            bpm_a_eff = sr * 60 / period_a
            bpm_corr  = sr * 60 / (period_a / ratio_c * ratio_c)  # = bpm_a_eff (target)
            print(f"    [drift-corr] {err_s:+.1f}ms drift → ratio {ratio:.6f}→{ratio_c:.6f} "
                  f"({(ratio_c/ratio - 1)*100:+.4f}%), expected drift ≈0ms")
            best["blend"] = blend_c
            best["b"]     = b_c
            best["n"]     = n_c
            best["trim"]  = trim_c

    # ── EQ blend (v2) ────────────────────────────────────────────────────────
    # Measurement blends above used equal-power (clean CV/phase scores).
    # Re-derive the final blend from the selected A/B zones using per-band EQ
    # curves.  Must happen AFTER offset selection + drift correction so we use
    # the correct trim position.
    if USE_EQ_BLEND:
        _za = samples_a[outro_sample : outro_sample + best["n"]]
        _zb = best["b"][:best["n"]]
        best["blend"] = _eq_blend(_za, _zb, best["n"], sr)

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
        "trim":         best["trim"],
        "blend":        best["blend"],
        "b_full":       best["b"],
        "sr":           sr,
        "period_a":     period_a,
        "cue_b":        int(cue),
        "stretch_ratio": float(ratio),
        "anchor_b_s":   float(anchor_b_s),
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

        _default_mix_in = curr.get("mix_in_bars", 16)
        _seen, MIX_IN_ATTEMPTS = set(), []
        for _v in [_default_mix_in, 16, 32, 8, 48, 0, 24]:
            if _v not in _seen:
                _seen.add(_v)
                MIX_IN_ATTEMPTS.append(_v)
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

    MAX_BODY_SEC = 180  # hard cap: no song body > 3 minutes

    mix_audio, mix_len, snippet_clips = None, 0, []
    _, sr = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))

    def _reblend(a_audio, b_audio, cf_len):
        """EQ-style crossfade for capped-body reblends (v2). Falls back to equal-power when USE_EQ_BLEND=False."""
        n = min(len(a_audio), len(b_audio), cf_len)
        if USE_EQ_BLEND:
            return _eq_blend(a_audio, b_audio, n, sr)
        return np.clip(
            a_audio[:n] * _equal_power(n, fade_in=False)[:, np.newaxis] +
            b_audio[:n] * _equal_power(n, fade_in=True)[:, np.newaxis],
            -1.0, 1.0,
        )

    for idx in range(len(tracks)):
        if idx == 0:
            tr0    = transitions[0]["tr"]
            raw, _ = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))

            # Cap body at 3 min; if capped, recompute blend from that point
            body_end = min(tr0["outro_sample"], int(MAX_BODY_SEC * sr))
            body = raw[:body_end]
            capped = body_end < tr0["outro_sample"]
            blend_audio = _reblend(raw[body_end:], tr0["b_full"], tr0["cf_len"]) if capped else tr0["blend"]

            mix_audio = body
            mix_len   = len(body)
            blend_start = mix_len
            mix_audio = np.concatenate([mix_audio, blend_audio], axis=0)
            mix_len  += len(blend_audio)

            blend_end = blend_start + len(blend_audio)
            print(f"  [body] {tracks[0]['name']}: {body_end/sr:.0f}s{' (capped)' if capped else ''}")
            snippet_clips.append({
                "idx":         1,
                "name_a":      transitions[0]["prev"]["name"],
                "name_b":      transitions[0]["curr"]["name"],
                "label_b":     transitions[0]["curr"].get("label", transitions[0]["curr"]["name"]),
                "start":       max(0, blend_start - snippet_sec * sr),
                "end":         blend_end + snippet_sec * sr,
                "blend_start": blend_start,
                "blend_end":   blend_end,
            })

        elif idx < len(transitions):
            tr_prev = transitions[idx - 1]["tr"]
            tr_next = transitions[idx]["tr"]

            # Body: stretched audio at tr_prev["period_a"] BPM — continuous from blend-in.
            # (Switching to native BPM here causes the audible BPM jump the user hears.)
            b_s = tr_prev["samples_b_s"]
            # outro_stretched: position in b_s (which starts at cue_b into native B)
            # corresponding to outro_sample in the full native track.
            # Wrong formula: outro_sample × len(b_s)/len(native_full)  -- ignores cue offset
            # Right formula:  (outro_sample - cue_b) × stretch_ratio
            cue_b   = tr_prev.get("cue_b", 0)
            ratio_b = tr_prev.get("stretch_ratio", 1.0)
            outro_stretched = int((tr_next["outro_sample"] - cue_b) * ratio_b)

            body_start = tr_prev["trim"] + tr_prev["cf_len"]

            # Cap body at 3 min, snapped to bar boundary in playing (stretched) BPM.
            # Snap backward from outro_stretched in whole-bar steps so body_end lands
            # on the same bar phase as outro_stretched — matching the phase that B's
            # trim was aligned to. Forward-snap from body_start lands on a different
            # bar phase when outro_stretched isn't at beat 0 → B sounds off by a beat.
            bar_samples = 4.0 * tr_prev["period_a"]
            max_body_samples = int(MAX_BODY_SEC * sr)
            raw_body_dur = outro_stretched - body_start
            if raw_body_dur > max_body_samples:
                max_end = body_start + max_body_samples
                k = math.ceil((outro_stretched - max_end) / bar_samples)
                body_end = int(round(outro_stretched - k * bar_samples))
                while body_end > max_end:
                    k += 1
                    body_end = int(round(outro_stretched - k * bar_samples))
                capped = True
            else:
                body_end = outro_stretched
                capped = False

            b_body = b_s[body_start : body_end].copy()
            body_dur_s = len(b_body) / sr
            print(f"  [body] {transitions[idx-1]['curr']['name']}: {body_dur_s:.0f}s{' (capped)' if capped else ''}")

            # Use pre-computed blend (both sides already beat-aligned at outgoing native BPM).
            # If body was capped and BPMs differ, the body runs at the PREVIOUS A's period while
            # b_full runs at the NEXT A's (native) period → beats drift during the crossfade.
            # Fix: ramp body BPM → native, snap body_end to a native bar boundary, then reblend
            # using samples_a (native A audio) so both sides of _reblend are at the same BPM.
            if body_end < outro_stretched:
                body_period   = tr_prev["period_a"]
                native_period = tr_next["period_a"]
                if abs(body_period / native_period - 1.0) > 0.001:
                    # BPM mismatch in capped reblend — fix it.
                    cue_b_prev      = tr_prev["cue_b"]
                    ratio_prev      = tr_prev["stretch_ratio"]
                    anchor_b_s_prev = tr_prev.get("anchor_b_s", 0.0)

                    # Convert body_end to native track coordinates.
                    native_body_end  = cue_b_prev + body_end / ratio_prev

                    # Snap backward from outro_sample in whole-bar steps so native_bar_end
                    # has the same bar phase as outro_sample — matching B's trim alignment.
                    native_outro = tr_next["outro_sample"]
                    native_bar_samples = 4.0 * native_period
                    k_n = math.ceil((native_outro - native_body_end) / native_bar_samples)
                    native_bar_end = int(round(native_outro - k_n * native_bar_samples))
                    while native_bar_end > native_body_end:
                        k_n += 1
                        native_bar_end = int(round(native_outro - k_n * native_bar_samples))

                    # Re-slice body to match the native bar boundary.
                    body_end_fix = max(body_start, int(round((native_bar_end - cue_b_prev) * ratio_prev)))
                    b_body = b_s[body_start:body_end_fix].copy()

                    # Ramp body BPM → native BPM over the last RAMP_BARS bars.
                    ramp_ratio = native_period / body_period
                    bpm_from   = sr * 60 / body_period
                    bpm_to     = sr * 60 / native_period
                    print(f"    [capped-ramp] {transitions[idx-1]['curr']['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM")
                    b_body = _bpm_ramp(b_body, sr, ramp_ratio, body_period)

                    # Both sides now at native BPM — beats stay aligned through the whole blend.
                    blend_audio = _reblend(
                        tr_next["samples_a"][native_bar_end:],
                        tr_next["b_full"],
                        tr_next["cf_len"],
                    )
                else:
                    blend_audio = _reblend(b_s[body_end:], tr_next["b_full"], tr_next["cf_len"])
            else:
                blend_audio = tr_next["blend"].copy()

            # BPM ramp: gradually nudge body BPM → blend native BPM over the last RAMP_BARS
            # bars. Applied to ALL non-capped bodies (RAMP_THRESHOLD=0.0). When BPMs match
            # exactly (ratio=1.0), the inner guard in _bpm_ramp skips all pyrubberband calls.
            # Capped bodies with BPM mismatch are handled above; same-BPM capped skip ramp.
            if not capped:
                ramp_ratio = tr_next["period_a"] / tr_prev["period_a"]
                if abs(ramp_ratio - 1.0) > RAMP_THRESHOLD:
                    bpm_from = sr * 60 / tr_prev["period_a"]
                    bpm_to   = sr * 60 / tr_next["period_a"]
                    print(f"    [ramp] {transitions[idx-1]['curr']['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM over {RAMP_BARS} bars")
                    b_body = _bpm_ramp(b_body, sr, ramp_ratio, tr_prev["period_a"])

            # 5ms micro-crossfade at body→blend splice.
            # Body uses stretched audio from the PREVIOUS transition's build; blend uses native
            # audio loaded fresh in the NEXT transition's build. Different processing chains of
            # the same source → sample values don't match exactly → audible click without this.
            micro_n = int(0.005 * sr)
            if micro_n > 0 and len(b_body) >= micro_n and len(blend_audio) >= micro_n:
                t = np.linspace(0.0, 1.0, micro_n)[:, np.newaxis]
                b_body[-micro_n:] = b_body[-micro_n:] * (1.0 - t) + blend_audio[:micro_n] * t
                blend_audio = blend_audio[micro_n:]

            blend_start = mix_len + len(b_body)
            mix_audio = np.concatenate([mix_audio, b_body, blend_audio], axis=0)
            mix_len  += len(b_body) + len(blend_audio)

            blend_end = blend_start + len(blend_audio)
            snippet_clips.append({
                "idx":         idx + 1,
                "name_a":      transitions[idx]["prev"]["name"],
                "name_b":      transitions[idx]["curr"]["name"],
                "label_b":     transitions[idx]["curr"].get("label", transitions[idx]["curr"]["name"]),
                "start":       max(0, blend_start - snippet_sec * sr),
                "end":         blend_end + snippet_sec * sr,
                "blend_start": blend_start,
                "blend_end":   blend_end,
            })

        else:
            tr_prev   = transitions[-1]["tr"]
            last_body = tr_prev["samples_b_s"][tr_prev["trim"] + tr_prev["cf_len"]:]
            mix_audio = np.concatenate([mix_audio, last_body], axis=0)
            mix_len  += len(last_body)

    total_min = len(mix_audio) / sr / 60
    print(f"  Full mix: {total_min:.1f} min")

    # ── Amplitude continuity check at every blend boundary ────────────────────
    # 2-second window: wide enough to catch any loud transient near the seam
    # 2-second window for blend boundaries; threshold 3.0x accounts for normal
    # musical dynamics over a 2s span (narrow 300ms window needed 2.5x, but 2s
    # smooths most transients — only flag true construction gaps).
    print(f"\n  Checking blend boundaries (RMS ratio threshold 3.0x, 2s window)...")
    window = int(2.0 * sr)
    CUT_THRESHOLD = 3.0
    cut_found = False
    for clip in snippet_clips:
        bs = clip.get("blend_start", 0)
        be = clip.get("blend_end", 0)
        label = f"{clip['name_a']}→{clip['name_b']}"

        # blend-in: body ends, new track starts fading in
        if bs >= window and bs + window < len(mix_audio):
            pre  = float(np.sqrt(np.mean(_mono(mix_audio[bs - window: bs]) ** 2))) + 1e-9
            post = float(np.sqrt(np.mean(_mono(mix_audio[bs: bs + window]) ** 2))) + 1e-9
            ratio = max(pre, post) / min(pre, post)
            sym = "✓" if ratio < CUT_THRESHOLD else "✗ CUT"
            print(f"    [{clip['idx']:02d}] blend-in   {label:<32}  RMS ratio {ratio:.2f}  {sym}")
            if ratio >= CUT_THRESHOLD:
                cut_found = True

        # blend-out: outgoing track has faded, body of incoming track begins
        if be >= window and be + window < len(mix_audio):
            pre  = float(np.sqrt(np.mean(_mono(mix_audio[be - window: be]) ** 2))) + 1e-9
            post = float(np.sqrt(np.mean(_mono(mix_audio[be: be + window]) ** 2))) + 1e-9
            ratio = max(pre, post) / min(pre, post)
            sym = "✓" if ratio < CUT_THRESHOLD else "✗ CUT"
            print(f"    [{clip['idx']:02d}] blend-out  {label:<32}  RMS ratio {ratio:.2f}  {sym}")
            if ratio >= CUT_THRESHOLD:
                cut_found = True

    if cut_found:
        print("  !! WARNING: amplitude discontinuity detected — check the flagged transitions")
    else:
        print("  All blend boundaries clean ✓")

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

    # ── Auto-generate CUE SHEET from actual blend times ──────────────────────
    def _ts(samples):
        s = int(samples / sr)
        return f"{s // 60:02d}:{s % 60:02d}"

    cf_dur_s = round(snippet_clips[0]["blend_end"] - snippet_clips[0]["blend_start"]) / sr if snippet_clips else 0
    first_label = tracks[0].get("label", tracks[0]["name"])
    cue_lines = [
        f"\n── CUE SHEET ──────────────────────────────────────────────────────────────────",
        f"  Each crossfade is ~{int(cf_dur_s)}s long.",
        f"",
        f"  00:00        Set starts — {first_label}",
    ]
    for clip in snippet_clips:
        bs = _ts(clip["blend_start"])
        be = _ts(clip["blend_end"])
        label = clip.get("label_b", clip["name_b"])
        n = clip["idx"]
        suffix = "  ← PEAK" if label in ("Rampa - The Touch",) else ("  ← close" if "Stimming" in label else "")
        cue_lines.append(f"  {bs}–{be}  [{n:02d}] → {label}{suffix}")

    set_end_s = int(len(mix_audio) / sr)
    cue_lines.append(f"  {set_end_s // 60:02d}:{set_end_s % 60:02d}         Set ends")
    cue_sheet = "\n".join(cue_lines)

    # Strip any existing CUE SHEET block from the brain's set_notes string
    notes_body = set_notes
    if "── CUE SHEET" in notes_body:
        notes_body = notes_body[:notes_body.index("── CUE SHEET")].rstrip()

    notes_path = os.path.join(out_dir, "SET_NOTES.txt")
    with open(notes_path, "w") as f:
        f.write(notes_body + cue_sheet + "\n")
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
