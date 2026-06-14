#!/usr/bin/env python3
"""
End-to-end blend quality tests.

Builds a transition snippet and checks each zone independently:
  - PRE zone  (Song A clean) → BPM must match A
  - BLEND zone               → IBI CV must be < 0.05 (beats are regular)
  - POST zone (Song B clean) → BPM must match B

If POST doesn't match B's BPM, something went wrong in the alignment.

Run:  python -m pytest tests/test_blend_quality.py -v -s
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
import librosa
import soundfile as sf
from pydub import AudioSegment

from mixer.transition import _seg_to_f32, _f32_to_seg, _equal_power, find_cue_point, _time_stretch_samples
from mixer.beatgrid import get_or_analyze, snap_to_beat

TRACK_A    = "downloads/library/cYgIjYOCHsw.mp3"   # Daily Twist ~122 BPM
TRACK_B    = "downloads/library/xrlH0SvEWB4.mp3"   # The Ride    ~122 BPM
BPM_HINT_A = 123.0
BPM_HINT_B = 123.0

OUT_DIR       = "output/transitions"
PRE_SEC       = 3.0    # seconds of A before the crossfade
POST_SEC      = 6.0    # seconds of B after the crossfade (more = more reliable BPM reading)
CF_BARS       = 8
OUTRO_BARS    = 16

CV_THRESHOLD  = 0.05
BPM_TOLERANCE = 1.5    # BPM — tolerance for the clean zones


def _bpm_from_file(path: str) -> tuple[float, float, int]:
    """Return (detected_bpm, ibi_cv, n_beats) for a short audio file."""
    try:
        from beat_this.inference import File2Beats
        f2b = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)
        beats, _ = f2b(path)
    except Exception:
        y, sr = librosa.load(path, sr=None, mono=True)
        _, frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = librosa.frames_to_time(frames, sr=sr)

    if len(beats) < 4:
        return 0.0, 1.0, len(beats)

    ibi    = np.diff(beats) * 1000
    mean   = float(np.mean(ibi))
    cv     = float(np.std(ibi) / mean)
    bpm    = 60000.0 / mean
    return round(bpm, 3), round(cv, 4), len(beats)


def _write_slice(samples: np.ndarray, sr: int, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _f32_to_seg(samples, sr).export(path, format="mp3", bitrate="192k")


@pytest.fixture(scope="module")
def transition():
    """
    Build the best A→B transition (lowest IBI CV across 4 beat offsets).
    Returns a dict with the snippet file paths and per-zone metrics.
    """
    if not os.path.exists(TRACK_A) or not os.path.exists(TRACK_B):
        pytest.skip("Tracks not downloaded")

    os.makedirs(OUT_DIR, exist_ok=True)

    grid_a = get_or_analyze(TRACK_A, hint_bpm=BPM_HINT_A)
    grid_b = get_or_analyze(TRACK_B, hint_bpm=BPM_HINT_B)

    seg_a = AudioSegment.from_file(TRACK_A).set_channels(2)
    seg_b = AudioSegment.from_file(TRACK_B).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    anchor_a = float(grid_a["beat_anchor_sample"])
    anchor_b = float(grid_b["beat_anchor_sample"])
    period_a = float(grid_a["beat_period_samples"])
    period_b = float(grid_b["beat_period_samples"])

    # Cue B past silence
    cue = find_cue_point(seg_b)
    if cue > anchor_b:
        cue = 0
    samples_b = samples_b[cue:]
    anchor_b -= cue

    # Stretch B to A's tempo
    ratio = period_a / period_b
    if abs(ratio - 1.0) > 0.001:
        samples_b = _time_stretch_samples(samples_b, sr, ratio)
    anchor_b_s = anchor_b * ratio

    # Snap A's outro to its beat grid
    outro_target = len(samples_a) - OUTRO_BARS * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    cf_len       = int(round(CF_BARS * 4 * period_a))
    pre_len      = int(PRE_SEC * sr)
    post_len     = int(POST_SEC * sr)

    best = {"cv": 1e9}
    for offset in range(4):
        trim = int(round(anchor_b_s + offset * period_a))
        trim = max(0, min(trim, len(samples_b) - sr))
        b    = samples_b[trim:]
        n    = min(cf_len, len(b))

        zone_a = samples_a[outro_sample: outro_sample + n]
        zone_b = b[:n]
        fo = _equal_power(n, fade_in=False)[:, np.newaxis]
        fi = _equal_power(n, fade_in=True)[:, np.newaxis]
        blend = np.clip(zone_a * fo + zone_b * fi, -1.0, 1.0)

        tmp = f"/tmp/_cand_blend_{offset}.mp3"
        _write_slice(blend, sr, tmp)
        bpm, cv, nb = _bpm_from_file(tmp)
        print(f"  offset +{offset}: BPM={bpm:.2f}  CV={cv:.4f}  beats={nb}")

        if cv < best["cv"]:
            best = {"cv": cv, "blend": blend, "b_full": b, "n": n, "offset": offset,
                    "trim": trim, "bpm_blend": bpm, "nb": nb}

    blend    = best["blend"]
    b_full   = best["b_full"]
    n        = best["n"]

    # Pre zone: last PRE_SEC of Song A before crossfade
    pre  = samples_a[max(0, outro_sample - pre_len): outro_sample]
    # Post zone: first POST_SEC of Song B after crossfade
    post = b_full[n: n + post_len]

    pre_path   = f"{OUT_DIR}/DailyTwist_PRE_A_clean.mp3"
    blend_path = f"{OUT_DIR}/DailyTwist_into_TheRide_BLEND.mp3"
    post_path  = f"{OUT_DIR}/TheRide_POST_B_clean.mp3"
    full_path  = f"{OUT_DIR}/DailyTwist_into_TheRide_FULL.mp3"

    _write_slice(pre,   sr, pre_path)
    _write_slice(blend, sr, blend_path)
    _write_slice(post,  sr, post_path)
    full = np.concatenate([pre, blend, post], axis=0)
    _write_slice(full,  sr, full_path)

    print(f"\n  Winner offset: +{best['offset']}")
    print(f"  Files in: {OUT_DIR}/")
    return {
        "pre_path":   pre_path,
        "blend_path": blend_path,
        "post_path":  post_path,
        "full_path":  full_path,
        "bpm_a":      grid_a["bpm"],
        "bpm_b":      grid_b["bpm"],
        "sr":         sr,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_pre_zone_matches_song_a_bpm(transition):
    """The 3s of Song A before the crossfade must be at A's BPM."""
    bpm, cv, nb = _bpm_from_file(transition["pre_path"])
    expected = transition["bpm_a"]
    print(f"\n  PRE (Song A clean): BPM={bpm:.3f}  expected={expected:.3f}  CV={cv:.4f}  beats={nb}")
    assert nb >= 3, f"Only {nb} beats detected in PRE zone — too short to measure"
    assert abs(bpm - expected) < BPM_TOLERANCE, (
        f"PRE zone BPM {bpm:.3f} is {abs(bpm-expected):.2f} off Song A's {expected:.3f}"
    )


def test_blend_zone_ibi_cv(transition):
    """IBI CV in the blend must be < 0.05 — beats must be locked together."""
    bpm, cv, nb = _bpm_from_file(transition["blend_path"])
    expected = transition["bpm_a"]
    print(f"\n  BLEND zone:         BPM={bpm:.3f}  expected={expected:.3f}  CV={cv:.4f}  beats={nb}")
    assert cv < CV_THRESHOLD, (
        f"BLEND IBI CV {cv:.4f} >= {CV_THRESHOLD} — beats are drifting during crossfade"
    )


def test_blend_zone_bpm(transition):
    """BPM detected in the blend must still match (tempo didn't wander)."""
    bpm, cv, nb = _bpm_from_file(transition["blend_path"])
    expected = transition["bpm_a"]
    assert abs(bpm - expected) < BPM_TOLERANCE, (
        f"BLEND BPM {bpm:.3f} is {abs(bpm-expected):.2f} off expected {expected:.3f}"
    )


def test_post_zone_matches_song_b_bpm(transition):
    """The 6s of Song B after the crossfade must be at B's BPM."""
    bpm, cv, nb = _bpm_from_file(transition["post_path"])
    expected = transition["bpm_b"]
    print(f"\n  POST (Song B clean): BPM={bpm:.3f}  expected={expected:.3f}  CV={cv:.4f}  beats={nb}")
    assert nb >= 3, f"Only {nb} beats detected in POST zone — too short to measure"
    assert abs(bpm - expected) < BPM_TOLERANCE, (
        f"POST zone BPM {bpm:.3f} is {abs(bpm-expected):.2f} off Song B's {expected:.3f}"
    )
