#!/usr/bin/env python3
"""
Test snippet generator with automated beat-alignment validation.

Strategy:
  1. Generate crossfade with current beat grid
  2. Run beat analysis on the output snippet
  3. Check: does the snippet BPM match the source tracks?
            is the IBI (inter-beat interval) consistent?
  4. If not → try shifting B's trim by 0, 1, 2, 3 beats and pick best
  5. Export winner

A passing blend has:
  - Detected BPM within ±0.5 of target
  - IBI coefficient of variation < 0.05 (very regular beats)
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import librosa
from pydub import AudioSegment
from mixer.transition import crossfade, _seg_to_f32, _f32_to_seg, find_cue_point, _equal_power, _time_stretch_samples
from mixer.beatgrid import get_or_analyze, snap_to_beat, load_grid_cache

TRACK_A = "downloads/library/cYgIjYOCHsw.mp3"
TRACK_B = "downloads/library/xrlH0SvEWB4.mp3"
BPM_A, BPM_B = 123.0, 123.0
PRE_MS, POST_MS = 3000, 3000
os.makedirs("output/snippets", exist_ok=True)


# ── Beat quality analysis ─────────────────────────────────────────────────────

def analyze_blend_quality(path: str, expected_bpm: float) -> dict:
    """
    Load a snippet and measure beat regularity.
    Returns metrics + pass/fail verdict.
    """
    y, sr = librosa.load(path, sr=None, mono=True)
    try:
        from beat_this.inference import File2Beats
        f2b = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)
        beats, _ = f2b(path)
    except Exception:
        _, frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = librosa.frames_to_time(frames, sr=sr)

    if len(beats) < 4:
        return {"pass": False, "reason": "too few beats detected"}

    ibi_ms = np.diff(beats) * 1000
    mean_ibi = float(np.mean(ibi_ms))
    cv       = float(np.std(ibi_ms) / mean_ibi)
    det_bpm  = 60000.0 / mean_ibi
    bpm_err  = abs(det_bpm - expected_bpm)

    passed = cv < 0.05 and bpm_err < 1.0
    return {
        "pass":        passed,
        "detected_bpm": round(det_bpm, 3),
        "expected_bpm": expected_bpm,
        "bpm_error":   round(bpm_err, 3),
        "ibi_cv":      round(cv, 4),
        "ibi_mean_ms": round(mean_ibi, 1),
        "n_beats":     len(beats),
        "reason":      "ok" if passed else f"BPM err {bpm_err:.2f} / IBI CV {cv:.3f}",
    }


def print_quality(q: dict, label: str = ""):
    mark = "✓ PASS" if q["pass"] else "✗ FAIL"
    print(f"  {mark}  {label}")
    print(f"    BPM: {q['detected_bpm']:.3f} (expected {q['expected_bpm']}, err {q['bpm_error']:.3f})")
    print(f"    IBI CV: {q['ibi_cv']:.4f}  (< 0.05 = good)")
    print(f"    Beats detected: {q['n_beats']}  ({q['reason']})")


# ── Core blend with phase-offset search ──────────────────────────────────────

def make_blend_with_validation(
    path_a: str, path_b: str, bpm_a: float, bpm_b: float,
    out_prefix: str, cf_bars: int = 8, outro_bars: int = 16,
    max_candidates: int = 4,
):
    """
    Try up to max_candidates beat offsets for B's trim, pick the best one
    (lowest IBI CV in the blended output). Exports winning snippet.
    """
    grid_a = get_or_analyze(path_a, hint_bpm=bpm_a)
    grid_b = get_or_analyze(path_b, hint_bpm=bpm_b)

    period_a = grid_a["beat_period_samples"]
    period_b = grid_b["beat_period_samples"]
    anchor_a = float(grid_a["beat_anchor_sample"])
    anchor_b = float(grid_b["beat_anchor_sample"])
    sr       = grid_a["sr"]
    bpm_a_g  = grid_a["bpm"]
    bpm_b_g  = grid_b["bpm"]

    seg_a = AudioSegment.from_file(path_a).set_channels(2)
    seg_b = AudioSegment.from_file(path_b).set_channels(2)

    samples_a, _ = _seg_to_f32(seg_a)
    samples_b, _ = _seg_to_f32(seg_b)

    # Cue B
    cue_sample = find_cue_point(seg_b)
    if cue_sample > anchor_b:
        cue_sample = 0
    samples_b_cued  = samples_b[cue_sample:]
    anchor_b_cued   = anchor_b - cue_sample

    # Time-stretch B if needed — threshold 0.0001 (0.01%), not 0.1%
    # Even 0.5% BPM difference causes 100ms drift over 8 bars
    from mixer.transition import _time_stretch_samples, _equal_power
    stretch_ratio = period_a / period_b
    if abs(stretch_ratio - 1.0) > 0.0001:
        print(f"  Stretching B: {bpm_b_g:.4f} → {bpm_a_g:.4f} BPM (ratio {stretch_ratio:.6f})")
        samples_b_s = _time_stretch_samples(samples_b_cued, sr, stretch_ratio)
    else:
        samples_b_s = samples_b_cued
    anchor_b_s = anchor_b_cued * stretch_ratio

    # A outro position (fixed — snapped to A's beat grid)
    seconds_per_bar   = period_a / sr * 4
    outro_target_samp = len(samples_a) - outro_bars * 4 * period_a
    outro_target_samp = max(anchor_a + period_a, outro_target_samp)
    outro_sample = int(round(snap_to_beat(outro_target_samp, anchor_a, period_a)))
    crossfade_samples = int(round(cf_bars * 4 * period_a))

    # Reference analysis of track A at the outro (what good beats look like)
    expected_bpm = bpm_a_g

    best_result = None
    best_cv     = 1e9
    best_offset = 0

    print(f"\n  Trying {max_candidates} beat-phase candidates for B trim:")
    print(f"  {'Offset':>8}  {'BPM':>8}  {'IBI CV':>8}  Result")
    print(f"  {'-'*50}")

    for beat_offset in range(max_candidates):
        trim_b = int(round(anchor_b_s + beat_offset * period_a))
        trim_b = max(0, min(trim_b, len(samples_b_s) - sr))

        b_aligned = samples_b_s[trim_b:]
        n_b = len(b_aligned)
        if n_b < crossfade_samples:
            crossfade_ms_use = max(n_b // 2, sr)
        else:
            crossfade_ms_use = crossfade_samples

        # Build blend
        zone_a = samples_a[outro_sample: outro_sample + crossfade_ms_use]
        zone_b = b_aligned[:crossfade_ms_use]
        n      = min(len(zone_a), len(zone_b))
        from mixer.transition import _equal_power
        fo = _equal_power(n, fade_in=False)[:, np.newaxis]
        fi = _equal_power(n, fade_in=True)[:, np.newaxis]
        blend = np.clip(zone_a[:n] * fo + zone_b[:n] * fi, -1.0, 1.0)

        # Write candidate snippet
        cand_path = f"/tmp/cand_{beat_offset}.mp3"
        snippet_start = max(0, outro_sample - int(PRE_MS / 1000 * sr))
        snippet_end   = min(len(samples_a), outro_sample + crossfade_ms_use + int(POST_MS / 1000 * sr))
        pre_a  = samples_a[snippet_start:outro_sample]
        post_b = b_aligned[crossfade_ms_use: crossfade_ms_use + int(POST_MS / 1000 * sr)]
        snippet_arr = np.concatenate([pre_a, blend, post_b], axis=0)
        _f32_to_seg(snippet_arr, sr).export(cand_path, format="mp3", bitrate="192k")

        q = analyze_blend_quality(cand_path, expected_bpm)
        mark = "✓" if q["pass"] else "✗"
        print(f"  +{beat_offset} beats  {q['detected_bpm']:>8.3f}  {q['ibi_cv']:>8.4f}  {mark} {q['reason']}")

        if q["ibi_cv"] < best_cv:
            best_cv     = q["ibi_cv"]
            best_result = (blend, b_aligned, q, trim_b, beat_offset)
            best_offset = beat_offset

    # Export winner
    blend_w, b_aligned_w, q_w, trim_w, offset_w = best_result
    n_w = len(blend_w)
    part_a = samples_a[:outro_sample]
    rest_b = b_aligned_w[n_w:]
    full   = np.concatenate([part_a, blend_w, rest_b], axis=0)

    # Snippet
    cf_start_samp = outro_sample
    snip_start    = max(0, cf_start_samp - int(PRE_MS / 1000 * sr))
    snip_end      = min(len(full), cf_start_samp + n_w + int(POST_MS / 1000 * sr))
    snippet       = full[snip_start:snip_end]

    out = f"{out_prefix}.mp3"
    _f32_to_seg(snippet, sr).export(out, format="mp3", bitrate="256k")

    print(f"\n  Winner: +{offset_w} beat offset  (IBI CV {best_cv:.4f})")
    print_quality(q_w, label=os.path.basename(out))
    print(f'  Play: open "{out}"')
    return q_w


# ── Run tests ─────────────────────────────────────────────────────────────────

print("=" * 60)
print("TEST 0: Phase sanity — same section blended with itself")
print("        Beat detector MUST see source BPM + CV≈0")
print("=" * 60)

# Extract 8 bars from the middle of Daily Twist at a known beat
grid_a0 = get_or_analyze(TRACK_A, hint_bpm=BPM_A)
sr0 = grid_a0["sr"]
anchor0 = float(grid_a0["beat_anchor_sample"])
period0 = float(grid_a0["beat_period_samples"])
seg_src = AudioSegment.from_file(TRACK_A).set_channels(2)
samples_src, _ = _seg_to_f32(seg_src)

# Section: start at beat 50 (clean mid-track), length = 8 bars
section_start = int(round(anchor0 + 50 * period0))
section_len   = int(round(8 * 4 * period0))
section = samples_src[section_start: section_start + section_len]

# True self-blend: section + section at equal-power (should be clean)
n = len(section)
fo = _equal_power(n, fade_in=False)[:, np.newaxis]
fi = _equal_power(n, fade_in=True)[:, np.newaxis]
self_blend = np.clip(section * fo + section * fi, -1.0, 1.0)

self_blend_path = "/tmp/self_blend_test.mp3"
_f32_to_seg(self_blend, sr0).export(self_blend_path, format="mp3", bitrate="192k")
q0 = analyze_blend_quality(self_blend_path, grid_a0["bpm"])
print_quality(q0, label="Same section + same section (phase sanity)")
print()

print("=" * 60)
print("TEST 1: Self-mix (Daily Twist outro vs same outro section)")
print("        Both tracks play the same audio — must be perfect")
print("=" * 60)

# Both A and B start at A's outro beat — identical audio → perfect blend required
grid_sm = get_or_analyze(TRACK_A, hint_bpm=BPM_A)
sr_sm   = grid_sm["sr"]
anchor_sm = float(grid_sm["beat_anchor_sample"])
period_sm = float(grid_sm["beat_period_samples"])
seg_sm  = AudioSegment.from_file(TRACK_A).set_channels(2)
samp_sm, _ = _seg_to_f32(seg_sm)

outro_bars_sm = 16
outro_target  = len(samp_sm) - outro_bars_sm * 4 * period_sm
from mixer.beatgrid import snap_to_beat as _snap
outro_samp_sm = int(round(_snap(outro_target, anchor_sm, period_sm)))
cf_len_sm     = int(round(8 * 4 * period_sm))

section_sm = samp_sm[outro_samp_sm: outro_samp_sm + cf_len_sm]
n_sm = len(section_sm)
fo_sm = _equal_power(n_sm, fade_in=False)[:, np.newaxis]
fi_sm = _equal_power(n_sm, fade_in=True)[:, np.newaxis]
selfblend_sm = np.clip(section_sm * fo_sm + section_sm * fi_sm, -1.0, 1.0)

sm_path = "output/snippets/selfmix_test.mp3"
_f32_to_seg(selfblend_sm, sr_sm).export(sm_path, format="mp3", bitrate="256k")
q1 = analyze_blend_quality(sm_path, grid_sm["bpm"])
print_quality(q1, label="selfmix_test.mp3 (same outro section × 2)")
print(f'  Play: open "{sm_path}"')
print()

print()
print("=" * 60)
print("TEST 2: Daily Twist → The Ride")
print("=" * 60)
q2 = make_blend_with_validation(
    TRACK_A, TRACK_B, BPM_A, BPM_B,
    "output/snippets/transition_8bar",
    cf_bars=8, outro_bars=16,
)

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
for label, q in [("Self-mix", q1), ("Daily Twist → The Ride", q2)]:
    mark = "✓ PASS" if q["pass"] else "✗ FAIL"
    print(f"  {mark}  {label}  BPM={q['detected_bpm']:.3f}  CV={q['ibi_cv']:.4f}")
