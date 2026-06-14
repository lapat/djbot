"""
DJ set builder — builds a complete named set from a track list.

Usage:
  python build_set.py

Outputs go to output/<set_name>/:
  FULL_SET.mp3        — complete mix
  NN_A_into_B.mp3     — 12s transition snippets (all must pass <20ms phase error)
  SET_NOTES.txt       — creative concept + tracklist with keys, BPM, mood tags
"""
import os, sys, tempfile, json
import numpy as np
import soundfile as sf
from pydub import AudioSegment

sys.path.insert(0, os.path.dirname(__file__))
from mixer.beatgrid import get_or_analyze, snap_to_beat
from mixer.transition import (
    _seg_to_f32, _f32_to_seg, _equal_power,
    find_cue_point, _time_stretch_samples, _beat_this_phase_trim,
)

# ── Set configuration ─────────────────────────────────────────────────────────

SET_NAME = "hours_before_light"

SET_NOTES = """\
THE HOURS BEFORE LIGHT
A DJ set by Claude for Louis Lapat

There are hours that belong to no day — the suspended territory between 3 and 7 in the \
morning where the city exhales and the mind becomes its own mythology. This set begins \
there, with Solomun's Kreatur der Nacht, because that is what you are in those hours: \
something ancient navigating the dark by instinct. Yotto's Just Another Piano Track \
finds you at the window, the melody moving through you the way thoughts do when they're \
too large for words. Ben Böhmer's Breathing is a reminder that the body is still here, \
still asking for attention. Then Anyma and Chris Avantgarde bring the first signal back: \
Consciousness — something switches on, slow at first, a warmth behind the sternum. Jon \
Hopkins completes the awakening with Open Eye Signal, the subconscious floor cracking open, \
signals arriving from somewhere you can't name, and suddenly you know the night is ending. \
Stephan Bodzin pulls you out to the street with Boavista, the city beginning to move around \
you. WhoMadeWho and Adriatique's Miracle is the moment — the full sun of the set, the peak — \
because the miracle is simply that morning arrives again, that you made it through. ARTBAT's \
Breathe In is exactly that: the lungful of cold air outside. Horizon shows you the edge, \
the thin orange seam where night becomes something else. And Monolink's Burning Sun closes \
it without drama, the way the sun rises without asking permission, burning through whatever \
you were carrying. This is not a set about ecstasy. It is about survival and the grace that follows.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Solomun feat. Isolation Berlin — Kreatur der Nacht     11A  122 BPM  energy↗  dark
  02  Yotto — Just Another Piano Track                       10A  123 BPM  energy↑  melancholic
  03  Ben Böhmer, Nils Hoffmann & Malou — Breathing           9A  122 BPM  energy→  tender
  04  Anyma & Chris Avantgarde — Consciousness                 6A  124 BPM  energy↑↑ awakening
  05  Jon Hopkins — Open Eye Signal                            4A  122 BPM  energy↓  deep dive
  06  Stephan Bodzin — Boavista                                5A  124 BPM  energy↑  moving
  07  WhoMadeWho & Adriatique — Miracle                        5A  123 BPM  energy↑↑↑ PEAK
  08  ARTBAT — Breathe In                                      5B  127 BPM  energy↘  full breath
  09  ARTBAT — Horizon                                         4A  124 BPM  energy↗  wide open
  10  Monolink — Burning Sun                                  10A  122 BPM  energy↘  close

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  11A → 10A → 9A     (descending minor wheel — going deeper into the night)
  9A → 6A → 4A       (consciousness emerges, eye opens — 3+2 steps toward light)
  4A → 5A → 5A → 5B  (the ascent — adjacent steps climbing the wheel)
  5B → 4A → 10A      (descent into morning — closing the circle)
"""

TRACKS = [
    {
        "name":   "Kreatur",
        "label":  "Solomun - Kreatur der Nacht",
        "path":   "downloads/new_tracks/Zn28G5-6Jow.mp3",
        "hint":   122.0,
        "mix_in_bars": 8,
    },
    {
        "name":   "JustPiano",
        "label":  "Yotto - Just Another Piano Track",
        "path":   "downloads/new_tracks/MW9xQzimoV0.mp3",
        "hint":   123.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "Breathing",
        "label":  "Ben Bohmer - Breathing",
        "path":   "downloads/new_tracks/CGUFF7aXjTw.mp3",
        "hint":   122.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "Conscious",
        "label":  "Anyma & Chris Avantgarde - Consciousness",
        "path":   "downloads/new_tracks/DYh0fLDaxm0.mp3",
        "hint":   122.0,
        "mix_in_bars": 8,
    },
    {
        "name":   "OpenEye",
        "label":  "Jon Hopkins - Open Eye Signal",
        "path":   "downloads/new_tracks/Q04ILDXe3QE.mp3",
        "hint":   122.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "Boavista",
        "label":  "Stephan Bodzin - Boavista",
        "path":   "downloads/new_tracks/owlsglILb1E.mp3",
        "hint":   124.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "Miracle",
        "label":  "WhoMadeWho & Adriatique - Miracle",
        "path":   "downloads/new_tracks/FPA5r9GaasY.mp3",
        "hint":   123.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "BreatheIn",
        "label":  "ARTBAT - Breathe In",
        "path":   "downloads/new_tracks/1LnLTDWHiUg.mp3",
        "hint":   127.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "Horizon",
        "label":  "ARTBAT - Horizon",
        "path":   "downloads/new_tracks/50zeHzEwgoI.mp3",
        "hint":   124.0,
        "mix_in_bars": 16,
    },
    {
        "name":   "BurningSun",
        "label":  "Monolink - Burning Sun",
        "path":   "downloads/new_tracks/CRLw8p_vLls.mp3",
        "hint":   122.0,
        "mix_in_bars": 8,
    },
]

CF_BARS    = 8
OUTRO_BARS = 16
SNIPPET_SEC = 6    # ±6s around blend midpoint = 12s snippet
PHASE_THRESHOLD_MS = 20.0


# ── Phase measurement (blend-file linear regression) ─────────────────────────

def _phase_error_ms(blend_path):
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
    A_mat = np.column_stack([np.ones(n), i])
    coeffs, _, _, _ = np.linalg.lstsq(A_mat, beats, rcond=None)
    anchor_fit, period_fit = coeffs
    residuals = beats - (anchor_fit + i * period_fit)
    mid = n // 2
    err = float(np.mean(residuals[mid:])) - float(np.mean(residuals[:mid]))
    while err >  period_fit / 2: err -= period_fit
    while err < -period_fit / 2: err += period_fit
    return round(abs(err) * 1000, 1)


# ── Single transition builder ─────────────────────────────────────────────────

def build_one_transition(track_a, track_b, out_dir):
    """
    Beat-align A→B, validate phase error, return metrics dict.
    Writes blend file to out_dir for phase measurement.
    """
    grid_a = get_or_analyze(track_a["path"], hint_bpm=track_a["hint"])
    grid_b = get_or_analyze(track_b["path"], hint_bpm=track_b["hint"])

    bpm_a = grid_a["bpm"];  bpm_b = grid_b["bpm"]
    diff_pct = abs(bpm_a - bpm_b) / bpm_a * 100
    if diff_pct > 8.0:
        raise ValueError(f"BPM too far: {bpm_a:.1f} vs {bpm_b:.1f} ({diff_pct:.1f}%)")

    seg_a = AudioSegment.from_file(track_a["path"]).set_channels(2)
    seg_b = AudioSegment.from_file(track_b["path"]).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    period_a  = float(grid_a["beat_period_samples"])
    period_b  = float(grid_b["beat_period_samples"])
    anchor_a  = float(grid_a["beat_anchor_sample"])
    anchor_b  = float(grid_b["beat_anchor_sample"])

    cue = find_cue_point(seg_b)
    if cue > anchor_b:
        cue = 0
    samples_b = samples_b[cue:]
    anchor_b -= cue

    ratio = period_a / period_b
    if abs(ratio - 1.0) > 0.0001:
        samples_b_s = _time_stretch_samples(samples_b, sr, ratio)
    else:
        samples_b_s = samples_b.copy()
    anchor_b_s = anchor_b * ratio

    outro_target = len(samples_a) - OUTRO_BARS * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    cf_len       = int(round(CF_BARS * 4 * period_a))

    mix_in_samples = int(round(track_b.get("mix_in_bars", 16) * 4 * period_a))
    anchor_search  = anchor_b_s + mix_in_samples

    trim = _beat_this_phase_trim(
        samples_a, samples_b_s, sr,
        outro_sample, anchor_search, period_a, CF_BARS,
    )
    trim = max(0, min(trim, len(samples_b_s) - sr))

    # Best of ±1-beat offsets (minimize blend CV)
    best = {"cv": 1e9}
    for offset in range(-1, 3):
        t  = max(0, min(int(round(trim + offset * period_a)), len(samples_b_s) - sr))
        b  = samples_b_s[t:]
        za = samples_a[outro_sample: outro_sample + cf_len]
        zb = b[:cf_len]
        n  = min(len(za), len(zb))
        za, zb = za[:n], zb[:n]
        fo = _equal_power(n, fade_in=False)[:, np.newaxis]
        fi = _equal_power(n, fade_in=True)[:, np.newaxis]
        blend = np.clip(za * fo + zb * fi, -1.0, 1.0)
        tmp = f"/tmp/_set_cand_{offset}.mp3"
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

    tag = f"{track_a['name']}_into_{track_b['name']}"
    os.makedirs(out_dir, exist_ok=True)
    blend_path = os.path.join(out_dir, f"{tag}_BLEND.mp3")
    _f32_to_seg(best["blend"], sr).export(blend_path, format="mp3", bitrate="192k")

    phase_err = _phase_error_ms(blend_path)

    return {
        "tag":         tag,
        "bpm_a":       bpm_a,
        "bpm_b":       bpm_b,
        "phase_err_ms": phase_err,
        "samples_a":   samples_a,
        "samples_b_s": samples_b_s,
        "outro_sample": outro_sample,
        "cf_len":      best["n"],
        "blend":       best["blend"],
        "b_full":      best["b"],
        "sr":          sr,
        "period_a":    period_a,
    }


# ── Full mix assembly ─────────────────────────────────────────────────────────

def build_full_set():
    out_dir = os.path.join("output", SET_NAME)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'═'*65}")
    print(f"  Building: {SET_NAME.upper().replace('_',' ')}")
    print(f"  {len(TRACKS)} tracks  |  CF_BARS={CF_BARS}  |  OUTRO_BARS={OUTRO_BARS}")
    print(f"{'═'*65}\n")

    transitions = []
    mix_parts   = []   # list of (samples, sr) to concatenate
    snippet_meta = []  # for 12s clips

    # Load first track
    grid_0   = get_or_analyze(TRACKS[0]["path"], hint_bpm=TRACKS[0]["hint"])
    seg_0    = AudioSegment.from_file(TRACKS[0]["path"]).set_channels(2)
    samp_0, sr = _seg_to_f32(seg_0)
    print(f"  [01] {TRACKS[0]['label']}  —  {grid_0['bpm']:.2f} BPM  {TRACKS[0]['hint']} hint")

    # Accumulate mix as float32 array
    mix_audio = samp_0   # full first track

    for i in range(1, len(TRACKS)):
        prev = TRACKS[i - 1]
        curr = TRACKS[i]
        n_label = f"[{i+1:02d}]"

        print(f"\n  {n_label} {curr['label']}")
        print(f"       Building {prev['name']} → {curr['name']}...")

        # Try current mix_in_bars, then alternatives if it fails
        MIX_IN_ATTEMPTS = [curr.get("mix_in_bars", 16), 8, 0, 24, 32]
        tr = None
        phase_ms = None
        for attempt_mix_in in MIX_IN_ATTEMPTS:
            curr_attempt = dict(curr, mix_in_bars=attempt_mix_in)
            tr = build_one_transition(prev, curr_attempt, os.path.join("output/transitions", "hours"))
            phase_ms = tr["phase_err_ms"]
            if phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS:
                if attempt_mix_in != curr.get("mix_in_bars", 16):
                    print(f"       Retried with mix_in_bars={attempt_mix_in}")
                break
            print(f"       mix_in={attempt_mix_in}: {phase_ms}ms — retrying...")

        status = "✓" if (phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS) else "✗"
        print(f"       Phase error: {phase_ms}ms  {status}")

        if phase_ms is not None and phase_ms >= PHASE_THRESHOLD_MS:
            print(f"  !! FAIL: {prev['name']}→{curr['name']} phase={phase_ms}ms ≥ {PHASE_THRESHOLD_MS}ms")
            print(f"     All mix_in attempts exhausted — aborting set build.")
            sys.exit(1)

        # Record where blend starts in the growing mix (samples from start)
        blend_start_in_mix = len(mix_audio) - (len(mix_audio) - tr["outro_sample"])
        # Actually: outro_sample is relative to samples_a (the isolated track, not the full mix yet)
        # The mix so far has mix_audio. The blend starts at outro_sample within samples_a.
        # But samples_a was the previous track file, not the whole mix.
        # We need to track the absolute position in mix_audio.
        # The previous track's outro starts at tr["outro_sample"] from samples_a.
        # In mix_audio, that's at: (total_mix_len_before_prev_track + tr["outro_sample"])
        # We'll compute snippet_start_sample after we know where in the mix this lands.

        # Splice: replace mix tail from outro_sample onward with blend + rest_b
        # Find where samples_a starts in mix_audio
        # (mix_audio up to now ends at the end of prev track's audio)
        # We need to trim mix_audio to outro_sample of prev track.

        # The outro_sample is within tr["samples_a"] which was loaded fresh from prev path.
        # The mix_audio was assembled from all previous tracks + blends.
        # The current tail of mix_audio IS the body of the previous track.
        # We need to find where in mix_audio the outro_sample of the prev track falls.

        # Simple approach: mix_audio = [everything before prev-track-outro] + blend + rest_b
        # We keep a pointer: how many samples of the previous track are already in mix_audio.
        # Easiest: track the length of mix_audio just before adding each track.

        transitions.append({
            "tr":    tr,
            "prev":  prev,
            "curr":  curr,
            "phase_ms": phase_ms,
        })

    # Rebuild mix from scratch using transitions
    print(f"\n{'─'*65}")
    print("  Assembling full mix...")
    mix_audio = None
    mix_sample_count = 0   # running total of samples in mix_audio so far
    snippet_clips = []

    for idx in range(len(TRACKS)):
        grid = get_or_analyze(TRACKS[idx]["path"], hint_bpm=TRACKS[idx]["hint"])
        period = float(grid["beat_period_samples"])
        anchor = float(grid["beat_anchor_sample"])

        seg = AudioSegment.from_file(TRACKS[idx]["path"]).set_channels(2)
        raw, sr = _seg_to_f32(seg)

        if idx == 0:
            # First track: get stretched version (will be the body before first blend)
            # Actually, first track plays at its native tempo (it's track A of first pair)
            tr = transitions[0]["tr"]
            outro = tr["outro_sample"]
            # Everything before the outro
            body = raw[:outro]
            if mix_audio is None:
                mix_audio = body
            else:
                mix_audio = np.concatenate([mix_audio, body], axis=0)
            mix_sample_count += len(body)

            # Now add the blend
            blend = tr["blend"]
            blend_start_samples = mix_sample_count
            mix_audio = np.concatenate([mix_audio, blend], axis=0)
            mix_sample_count += len(blend)

            # Snippet: ±SNIPPET_SEC around midpoint
            mid = blend_start_samples + len(blend) // 2
            snip_s = max(0, mid - SNIPPET_SEC * sr)
            snip_e = mid + SNIPPET_SEC * sr
            snippet_clips.append({
                "idx":   1,
                "name_a": transitions[0]["prev"]["name"],
                "name_b": transitions[0]["curr"]["name"],
                "start": snip_s,
                "end":   snip_e,
            })

            # Track B body for next iteration
            prev_b_body = tr["b_full"][len(blend):]
            prev_b_sr   = sr

        else:
            if idx < len(transitions):
                # This track is both B of previous and A of next
                tr_prev = transitions[idx - 1]["tr"]
                tr_next = transitions[idx]["tr"]

                # B was already stretched by tr_prev; tr_next used a fresh load
                # We use tr_prev's b_full (stretched) up to tr_next's outro_sample
                # But tr_next's outro_sample is relative to tr_next's samples_b_s
                # which was the stretched version of TRACKS[idx].
                outro_in_b = tr_next["outro_sample"]
                b_s = tr_next["samples_b_s"]   # stretched version of TRACKS[idx]

                # We already added tr_prev's blend. Now add the body of TRACKS[idx]
                # up to its own outro (in stretched space).
                b_body = b_s[tr_prev["cf_len"]: outro_in_b]

                blend_start_samples = mix_sample_count + len(b_body)
                mix_audio = np.concatenate([mix_audio, b_body], axis=0)
                mix_sample_count += len(b_body)

                # Add blend
                blend = tr_next["blend"]
                mix_audio = np.concatenate([mix_audio, blend], axis=0)
                mix_sample_count += len(blend)

                mid = blend_start_samples + len(blend) // 2
                snip_s = max(0, mid - SNIPPET_SEC * sr)
                snip_e = mid + SNIPPET_SEC * sr
                snippet_clips.append({
                    "idx":   idx + 1,
                    "name_a": transitions[idx]["prev"]["name"],
                    "name_b": transitions[idx]["curr"]["name"],
                    "start": snip_s,
                    "end":   snip_e,
                })

            else:
                # Last track: play stretched remainder to end
                tr_prev = transitions[idx - 1]["tr"]
                b_s = tr_prev["samples_b_s"]
                last_body = b_s[tr_prev["cf_len"]:]
                mix_audio = np.concatenate([mix_audio, last_body], axis=0)
                mix_sample_count += len(last_body)

    total_min = len(mix_audio) / sr / 60
    print(f"  Full mix: {total_min:.1f} min  ({len(mix_audio):,} samples)")

    # Export full mix
    full_path = os.path.join(out_dir, "FULL_SET.mp3")
    print(f"  Exporting FULL_SET.mp3...")
    _f32_to_seg(mix_audio, sr).export(full_path, format="mp3", bitrate="256k")
    print(f"  ✓ {full_path}")

    # Export 12s snippets
    print(f"\n  Exporting transition snippets...")
    for clip in snippet_clips:
        s = int(clip["start"])
        e = min(int(clip["end"]), len(mix_audio))
        snippet = mix_audio[s:e]
        n_a = clip["name_a"]
        n_b = clip["name_b"]
        fname = f"{clip['idx']:02d}_{n_a}_into_{n_b}.mp3"
        spath = os.path.join(out_dir, fname)
        _f32_to_seg(snippet, sr).export(spath, format="mp3", bitrate="192k")
        dur = len(snippet) / sr
        print(f"  ✓ {fname}  ({dur:.1f}s)")

    # Write SET_NOTES.txt
    notes_path = os.path.join(out_dir, "SET_NOTES.txt")
    with open(notes_path, "w") as f:
        f.write(SET_NOTES)
    print(f"\n  ✓ {notes_path}")

    # Summary
    print(f"\n{'═'*65}")
    print(f"  SET COMPLETE: output/{SET_NAME}/")
    print(f"{'═'*65}")
    print(f"  Transitions (all must be < {PHASE_THRESHOLD_MS}ms):")
    for t in transitions:
        ms = t["phase_ms"]
        sym = "✓" if ms is not None and ms < PHASE_THRESHOLD_MS else "✗ FAIL"
        print(f"    {t['prev']['name']:<12} → {t['curr']['name']:<12}  {ms}ms  {sym}")
    print()


if __name__ == "__main__":
    build_full_set()
