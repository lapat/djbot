#!/usr/bin/env python3
"""
Tests for beatgrid.py — BPM detection and beat grid arithmetic.

Run:  python -m pytest tests/ -v
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
from mixer.beatgrid import _precise_bpm, snap_to_beat, get_or_analyze


# ── Unit: BPM normalization (octave-snap) ────────────────────────────────────

def _call_precise_bpm(hint: float, synth_bpm: float) -> float:
    """
    Synthesize a click track at synth_bpm, then call _precise_bpm with hint.
    Returns the detected BPM.
    """
    sr = 48000
    duration = 10.0
    period = sr * 60.0 / synth_bpm
    n_samples = int(sr * duration)
    y = np.zeros(n_samples, dtype=np.float32)
    # Place impulses at each beat
    pos = 0.0
    while pos < n_samples:
        idx = int(round(pos))
        if idx < n_samples:
            y[idx] = 1.0
        pos += period
    return _precise_bpm(y, sr, hint)


class TestBpmNormalization:
    """The octave-snap must bring detected BPM to the octave closest to hint."""

    def test_correct_octave_no_change_needed(self):
        # Hint and detected are already close — no octave adjustment
        detected = _call_precise_bpm(hint=122.0, synth_bpm=122.0)
        assert abs(detected - 122.0) < 3.0, f"Expected ~122, got {detected:.2f}"

    def test_halves_double_detection(self):
        # Track is at 79 BPM but detector might find 158; hint=79 should pull it back
        detected = _call_precise_bpm(hint=79.0, synth_bpm=79.0)
        assert detected < 110, f"Expected ~79, got {detected:.2f} (still doubled?)"
        assert abs(detected - 79.0) < 5.0, f"Expected ~79, got {detected:.2f}"

    def test_doubles_half_detection(self):
        # Track is at 126 BPM but detector might find 63; hint=126 should push it up
        detected = _call_precise_bpm(hint=126.0, synth_bpm=126.0)
        assert detected > 100, f"Expected ~126, got {detected:.2f} (still halved?)"
        assert abs(detected - 126.0) < 5.0, f"Expected ~126, got {detected:.2f}"

    def test_156_with_hint_79_normalizes_down(self):
        # Simulates Night Thoughts: detector returns 156 but hint is 79 → should halve
        detected = _call_precise_bpm(hint=79.0, synth_bpm=156.0)
        assert detected < 100, f"Expected ~78, got {detected:.2f} (not halved!)"

    def test_156_with_hint_156_stays_up(self):
        # If the hint says 156 (e.g. drum & bass), stay at 156
        detected = _call_precise_bpm(hint=156.0, synth_bpm=156.0)
        assert detected > 130, f"Expected ~156, got {detected:.2f} (unexpectedly halved)"

    def test_normalization_does_not_pingpong(self):
        # The old bug: 156.25 → /2=78.125 (< 80) → *2=156.25 (> 140) → infinite loop
        # Ensure calling _precise_bpm terminates and gives a sane result
        result = _call_precise_bpm(hint=79.0, synth_bpm=79.0)
        assert 60.0 < result < 200.0, f"Result {result:.2f} is out of any sane range"


# ── Unit: snap_to_beat ────────────────────────────────────────────────────────

class TestSnapToBeat:
    anchor = 12128.0
    period = 23552.7  # 122.28 BPM at 48000 Hz

    def test_snap_exactly_on_beat(self):
        beat_5 = self.anchor + 5 * self.period
        snapped = snap_to_beat(beat_5, self.anchor, self.period)
        assert abs(snapped - beat_5) < 0.001, "Snap of exact beat position should have zero error"

    def test_snap_half_beat_rounds_to_nearest(self):
        half = self.anchor + 5.5 * self.period
        snapped = snap_to_beat(half, self.anchor, self.period)
        # Should round to either beat 5 or beat 6
        err_5 = abs(snapped - (self.anchor + 5 * self.period))
        err_6 = abs(snapped - (self.anchor + 6 * self.period))
        assert min(err_5, err_6) < 1.0

    def test_snap_error_always_less_than_half_period(self):
        # For any arbitrary position, snap error < period/2
        for offset in [0.1, 0.3, 0.7, 0.9, 1.0, 2.5, 10.0, 99.9, 200.0]:
            target = self.anchor + offset * self.period
            snapped = snap_to_beat(target, self.anchor, self.period)
            err = abs(snapped - target)
            assert err <= self.period / 2 + 1, (
                f"Snap error {err:.1f} > half-period {self.period/2:.1f} for offset={offset}"
            )

    def test_snap_error_in_ms_is_tiny(self):
        sr = 48000
        # Snap from 1ms off — error should shrink to < 0.01ms
        target = self.anchor + 50 * self.period + sr * 0.001  # 1ms off
        snapped = snap_to_beat(target, self.anchor, self.period)
        err_ms = abs(snapped - (self.anchor + 50 * self.period)) / sr * 1000
        assert err_ms < 0.5, f"Snap error {err_ms:.3f}ms is too large"


# ── Integration: analyze real tracks ─────────────────────────────────────────

TRACKS = {
    "Daily Twist":     ("downloads/library/cYgIjYOCHsw.mp3", 123.0),
    "The Ride":        ("downloads/library/xrlH0SvEWB4.mp3", 123.0),
    "Sundancing":      ("downloads/library/5pEMHmHq8hY.mp3", 126.0),
    "Internet":        ("downloads/library/rz0Tinho9qM.mp3", 129.2),
    "Night Thoughts":  ("downloads/library/iIo9HZUt5qU.mp3", 79.0),
}

BPM_TOLERANCE = 2.0  # BPM — maximum allowed deviation from expected
ANCHOR_MAX_MS = 8000  # ms — anchor must be within first 8 seconds


@pytest.mark.parametrize("name,path_hint", TRACKS.items())
def test_track_bpm_within_tolerance(name, path_hint):
    path, expected_bpm = path_hint
    if not os.path.exists(path):
        pytest.skip(f"Track not downloaded: {path}")
    grid = get_or_analyze(path, hint_bpm=expected_bpm)
    detected = grid["bpm"]
    err = abs(detected - expected_bpm)
    assert err < BPM_TOLERANCE, (
        f"{name}: expected ~{expected_bpm} BPM, got {detected:.4f} (err={err:.2f})"
    )


@pytest.mark.parametrize("name,path_hint", TRACKS.items())
def test_beat_anchor_in_first_8_seconds(name, path_hint):
    path, expected_bpm = path_hint
    if not os.path.exists(path):
        pytest.skip(f"Track not downloaded: {path}")
    grid = get_or_analyze(path, hint_bpm=expected_bpm)
    sr = grid["sr"]
    anchor_ms = grid["beat_anchor_sample"] / sr * 1000
    assert anchor_ms <= ANCHOR_MAX_MS, (
        f"{name}: anchor at {anchor_ms:.0f}ms > {ANCHOR_MAX_MS}ms — likely missed the first kick"
    )


@pytest.mark.parametrize("name,path_hint", TRACKS.items())
def test_beat_period_matches_bpm(name, path_hint):
    path, expected_bpm = path_hint
    if not os.path.exists(path):
        pytest.skip(f"Track not downloaded: {path}")
    grid = get_or_analyze(path, hint_bpm=expected_bpm)
    sr = grid["sr"]
    computed_period = sr * 60.0 / grid["bpm"]
    assert abs(computed_period - grid["beat_period_samples"]) < 1.0, (
        f"{name}: beat_period_samples {grid['beat_period_samples']:.1f} "
        f"inconsistent with bpm {grid['bpm']:.4f}"
    )
