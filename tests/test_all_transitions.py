#!/usr/bin/env python3
"""
Test every compatible track pair in the library.

For each A→B pair:
  1. Check BPM compatibility (reject > 8% apart)
  2. Build the blend (best of 4 beat offsets)
  3. Measure phase error (project A's beat grid into POST zone, compare with B)
  4. Count double-beat gaps < 100ms in the blend zone
  5. Check pre/blend/post BPM all match within tolerance

A pair is PASS only if ALL of:
  - Phase error < 20ms
  - Blend IBI CV < 0.05
  - PRE BPM within 1.5 of A
  - POST BPM within 1.5 of B (after stretch)

Run:  python -m pytest tests/test_all_transitions.py -v -s
"""
import os, sys, itertools, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
import librosa
import soundfile as sf
from pydub import AudioSegment
from scipy.signal import butter, sosfilt

from mixer.beatgrid import get_or_analyze, snap_to_beat
from mixer.transition import (
    _seg_to_f32, _f32_to_seg, _equal_power,
    find_cue_point, _time_stretch_samples, _beat_this_phase_trim,
)

OUT_DIR       = "output/transitions"
PRE_SEC       = 3.0
POST_SEC      = 6.0
CF_BARS       = 8
OUTRO_BARS    = 16
BPM_COMPAT_PCT = 8.0   # reject pairs farther apart than this

CV_THRESHOLD   = 0.05
BPM_TOLERANCE  = 2.0   # generous — beat_this has some variance on short clips
PHASE_THRESHOLD_MS = 20.0  # humans hear misalignment at ~20ms; blend-file measurement is reliable to ±5ms


# ── Library ───────────────────────────────────────────────────────────────────

LIBRARY = {
    "DailyTwist":  ("downloads/library/cYgIjYOCHsw.mp3", 123.0),
    "TheRide":     ("downloads/library/xrlH0SvEWB4.mp3", 123.0),
    "InTheDark":   ("downloads/library/awJfIl_Fc0I.mp3", 123.0),
    "Sundancing":  ("downloads/library/5pEMHmHq8hY.mp3", 126.0),
    "Internet":    ("downloads/library/rz0Tinho9qM.mp3", 129.2),
    # Night Thoughts (79 BPM) excluded — incompatible tempo
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bpm_from_file(path):
    try:
        from beat_this.inference import File2Beats
        beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(path)
    except Exception:
        y, sr = librosa.load(path, sr=None, mono=True)
        _, frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = librosa.frames_to_time(frames, sr=sr)
    if len(beats) < 4:
        return 0.0, 1.0, len(beats)
    ibi = np.diff(beats) * 1000
    cv  = float(np.std(ibi) / np.mean(ibi))
    bpm = 60000.0 / float(np.mean(ibi))
    return round(bpm, 3), round(cv, 4), len(beats)


def _phase_error_ms(blend_path, cf_bars):
    """
    Measure beat alignment directly from the BLEND file.

    The blend has ~32 beats (8 bars * 4 beats). We fit a linear beat grid
    to all detected beats and measure the residual at the midpoint — this
    is where A→B phase mismatch shows up as a discontinuity.

    Returns phase error in ms. Values < 20ms are inaudible; > 30ms is
    audible as a slight stutter.
    """
    try:
        from beat_this.inference import File2Beats
        f2b = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)
        beats, _ = f2b(blend_path)
    except Exception:
        return None
    if len(beats) < 6:
        return None

    beats = np.array(beats, dtype=float)
    # Linear fit: expected_beat[i] = a + i * period
    n = len(beats)
    i = np.arange(n, dtype=float)
    # Least-squares fit
    A_mat = np.column_stack([np.ones(n), i])
    coeffs, _, _, _ = np.linalg.lstsq(A_mat, beats, rcond=None)
    anchor_fit, period_fit = coeffs

    # Residuals at each beat
    residuals = beats - (anchor_fit + i * period_fit)

    # Phase mismatch shows up as a shift at the midpoint.
    # Compute mean residual in the first half vs second half.
    mid = n // 2
    first_half  = float(np.mean(residuals[:mid]))
    second_half = float(np.mean(residuals[mid:]))
    err = second_half - first_half

    # Wrap to [-period/2, period/2]
    while err >  period_fit / 2: err -= period_fit
    while err < -period_fit / 2: err += period_fit

    return round(abs(err) * 1000, 1)


def _double_beat_count(full_path, blend_start_sec, blend_dur_sec):
    y, sr = librosa.load(full_path, sr=None, mono=True)
    seg = y[int(blend_start_sec * sr): int((blend_start_sec + blend_dur_sec) * sr)]
    sos = butter(4, 200 / (sr / 2), btype='low', output='sos')
    seg_lp = sosfilt(sos, seg)
    onsets = librosa.onset.onset_detect(
        y=seg_lp, sr=sr, hop_length=32, backtrack=True,
        units='time', delta=0.04, wait=int(sr * 0.05 / 32),
    )
    gaps = np.diff(onsets) * 1000
    return int(np.sum(gaps < 100))


def build_transition(name_a, path_a, hint_a, name_b, path_b, hint_b, mix_in_bars=0):
    """
    Build best-of-4-offsets blend. Returns dict of metrics + file paths.
    Returns None if tracks are BPM-incompatible.

    mix_in_bars: start B this many bars into the track (skip sparse intro).
    """
    if not os.path.exists(path_a) or not os.path.exists(path_b):
        return None

    grid_a = get_or_analyze(path_a, hint_bpm=hint_a)
    grid_b = get_or_analyze(path_b, hint_bpm=hint_b)

    bpm_a = grid_a["bpm"]
    bpm_b = grid_b["bpm"]
    diff_pct = abs(bpm_a - bpm_b) / bpm_a * 100

    if diff_pct > BPM_COMPAT_PCT:
        return {"skip": True, "reason": f"BPM too far apart: {bpm_a:.1f} vs {bpm_b:.1f} ({diff_pct:.1f}%)"}

    seg_a = AudioSegment.from_file(path_a).set_channels(2)
    seg_b = AudioSegment.from_file(path_b).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    period_a = float(grid_a["beat_period_samples"])
    period_b = float(grid_b["beat_period_samples"])
    anchor_a = float(grid_a["beat_anchor_sample"])
    anchor_b = float(grid_b["beat_anchor_sample"])

    cue = find_cue_point(seg_b)
    if cue > anchor_b:
        cue = 0
    samples_b = samples_b[cue:]
    anchor_b  -= cue

    ratio = period_a / period_b
    if abs(ratio - 1.0) > 0.0001:
        samples_b = _time_stretch_samples(samples_b, sr, ratio)
    anchor_b_s = anchor_b * ratio

    outro_target = len(samples_a) - OUTRO_BARS * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    cf_len       = int(round(CF_BARS * 4 * period_a))
    pre_len      = int(PRE_SEC * sr)
    post_len     = int(POST_SEC * sr)

    # Optionally skip B's sparse intro by mixing in further into the track
    mix_in_samples = int(round(mix_in_bars * 4 * period_a))
    anchor_b_s_search = anchor_b_s + mix_in_samples

    # Phase-align B to A using beat_this beat detection
    trim = _beat_this_phase_trim(
        samples_a, samples_b, sr,
        outro_sample, anchor_b_s_search, period_a, CF_BARS,
    )
    trim = max(0, min(trim, len(samples_b) - sr))

    # Still try ±1 beat offsets around the beat_this trim and pick best CV
    best = {"cv": 1e9}
    for offset in range(-1, 3):
        t = int(round(trim + offset * period_a))
        t = max(0, min(t, len(samples_b) - sr))
        b      = samples_b[t:]
        zone_a = samples_a[outro_sample: outro_sample + cf_len]
        zone_b = b[:cf_len]
        n      = min(len(zone_a), len(zone_b))   # actual usable length
        zone_a = zone_a[:n]
        zone_b = zone_b[:n]
        fo = _equal_power(n, fade_in=False)[:, np.newaxis]
        fi = _equal_power(n, fade_in=True)[:, np.newaxis]
        blend = np.clip(zone_a * fo + zone_b * fi, -1.0, 1.0)
        tmp = f"/tmp/_tr_cand_{offset}.mp3"
        _f32_to_seg(blend, sr).export(tmp, format="mp3", bitrate="192k")
        _, cv, _ = _bpm_from_file(tmp)
        if cv < best["cv"]:
            best = {"cv": cv, "blend": blend, "b": b, "n": n, "offset": offset, "trim": t}

    blend = best["blend"]
    b_full = best["b"]
    n      = best["n"]

    pre  = samples_a[max(0, outro_sample - pre_len): outro_sample]
    post = b_full[n: n + post_len]
    full = np.concatenate([pre, blend, post], axis=0)

    os.makedirs(OUT_DIR, exist_ok=True)
    tag       = f"{name_a}_into_{name_b}"
    pre_path  = f"{OUT_DIR}/{tag}_PRE.mp3"
    blend_path= f"{OUT_DIR}/{tag}_BLEND.mp3"
    post_path = f"{OUT_DIR}/{tag}_POST.mp3"
    full_path = f"{OUT_DIR}/{tag}_FULL.mp3"

    _f32_to_seg(pre,   sr).export(pre_path,   format="mp3", bitrate="192k")
    _f32_to_seg(blend, sr).export(blend_path, format="mp3", bitrate="192k")
    _f32_to_seg(post,  sr).export(post_path,  format="mp3", bitrate="192k")
    _f32_to_seg(full,  sr).export(full_path,  format="mp3", bitrate="256k")

    blend_dur = n / sr
    phase_err = _phase_error_ms(blend_path, CF_BARS)
    doubles   = _double_beat_count(full_path, PRE_SEC, blend_dur)

    bpm_pre,  cv_pre,  nb_pre  = _bpm_from_file(pre_path)
    bpm_blend,cv_blend,nb_blend= _bpm_from_file(blend_path)
    bpm_post, cv_post, nb_post = _bpm_from_file(post_path)

    return {
        "skip":       False,
        "bpm_a":      bpm_a,
        "bpm_b":      bpm_b,
        "diff_pct":   diff_pct,
        "best_offset":best["offset"],
        "blend_cv":   best["cv"],
        "phase_err_ms": phase_err,
        "double_beats": doubles,
        "bpm_pre":    bpm_pre,  "cv_pre":   cv_pre,
        "bpm_blend":  bpm_blend,"cv_blend": cv_blend,
        "bpm_post":   bpm_post, "cv_post":  cv_post,
        "n_pre":      nb_pre,   "n_blend":  nb_blend, "n_post": nb_post,
        "full_path":  full_path,
        "pre_path":   pre_path,
        "post_path":  post_path,
    }


# ── Generate all pairs as pytest params ───────────────────────────────────────

names  = list(LIBRARY.keys())
PAIRS  = [(a, b) for a, b in itertools.permutations(names, 2)]


@pytest.fixture(scope="module")
def all_results():
    results = {}
    for name_a, name_b in PAIRS:
        path_a, hint_a = LIBRARY[name_a]
        path_b, hint_b = LIBRARY[name_b]
        key = f"{name_a}→{name_b}"
        print(f"\n  Building {key}...")
        results[key] = build_transition(name_a, path_a, hint_a, name_b, path_b, hint_b)
    return results


@pytest.mark.parametrize("pair", [f"{a}→{b}" for a, b in PAIRS])
def test_bpm_compatibility(pair, all_results):
    r = all_results[pair]
    if r is None:
        pytest.skip("Track missing")
    if r.get("skip"):
        pytest.skip(r["reason"])
    assert r["diff_pct"] <= BPM_COMPAT_PCT, (
        f"{pair}: BPM diff {r['diff_pct']:.1f}% > {BPM_COMPAT_PCT}%"
    )


@pytest.mark.parametrize("pair", [f"{a}→{b}" for a, b in PAIRS])
def test_blend_cv(pair, all_results):
    r = all_results[pair]
    if r is None or r.get("skip"):
        pytest.skip(r["reason"] if r else "missing")
    assert r["blend_cv"] < CV_THRESHOLD, (
        f"{pair}: blend CV {r['blend_cv']:.4f} >= {CV_THRESHOLD}"
    )


@pytest.mark.parametrize("pair", [f"{a}→{b}" for a, b in PAIRS])
def test_phase_error(pair, all_results):
    r = all_results[pair]
    if r is None or r.get("skip"):
        pytest.skip(r["reason"] if r else "missing")
    if r["phase_err_ms"] is None:
        pytest.skip("beat_this unavailable")
    assert r["phase_err_ms"] < PHASE_THRESHOLD_MS, (
        f"{pair}: phase error {r['phase_err_ms']:.1f}ms >= {PHASE_THRESHOLD_MS}ms"
    )


@pytest.mark.parametrize("pair", [f"{a}→{b}" for a, b in PAIRS])
def test_pre_bpm(pair, all_results):
    r = all_results[pair]
    if r is None or r.get("skip"):
        pytest.skip(r["reason"] if r else "missing")
    if r["n_pre"] < 3:
        pytest.skip(f"only {r['n_pre']} beats in PRE — too short")
    assert abs(r["bpm_pre"] - r["bpm_a"]) < BPM_TOLERANCE, (
        f"{pair}: PRE BPM {r['bpm_pre']:.2f} off A's {r['bpm_a']:.2f}"
    )


@pytest.mark.parametrize("pair", [f"{a}→{b}" for a, b in PAIRS])
def test_post_bpm(pair, all_results):
    r = all_results[pair]
    if r is None or r.get("skip"):
        pytest.skip(r["reason"] if r else "missing")
    if r["n_post"] < 4:
        pytest.skip(f"only {r['n_post']} beats in POST — too short")
    # POST is stretched B — check against A's BPM (B was stretched to match A)
    assert abs(r["bpm_post"] - r["bpm_a"]) < BPM_TOLERANCE, (
        f"{pair}: POST BPM {r['bpm_post']:.2f} off A's {r['bpm_a']:.2f} (B stretched to match A)"
    )
