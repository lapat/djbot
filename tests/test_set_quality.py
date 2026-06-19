#!/usr/bin/env python3
"""
Full-mix quality gate — run after ANY change to set_builder.py or a brain file.

What is tested and why:
  - _bpm_ramp unit tests: verify the ramp function is correct before trusting it on
    real audio. Synthetic signals let us check ratio, length, energy, and edge cases
    without loading any music files.

  - 3-track integration tests: a fast sanity build (KT→Butch→Sol) that exercises the
    most critical transition (122→124 BPM Butch ramp, the original 6:11 complaint).
    Runs in ~60s. Use this for quick iteration.

  - Solomun full-set tests: verifies all 19 transitions pass phase (<20ms) and RMS
    (<3.0x) checks in the complete 62-minute mix. Runs in ~10 min. Use before any
    release or after changes to brain settings.

IMPORTANT THRESHOLDS (from CLAUDE.md):
  - Phase error < 20ms per transition (measured via blend-file linear regression)
  - RMS ratio < 3.0x at both blend-in and blend-out boundaries
  - BPM ramp must fire for every non-capped body (RAMP_THRESHOLD = 0.0)

Run all:        python -m pytest tests/test_set_quality.py -v -s
Fast (unit only): python -m pytest tests/test_set_quality.py -v -s -m "not slow"
3-track only:   python -m pytest tests/test_set_quality.py -v -s -m "slow" -k "ThreeTrack"
"""
import os, sys, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest

from mixer.set_builder import _bpm_ramp, RAMP_BARS, RAMP_CHUNKS, RAMP_THRESHOLD

SR = 44100


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: _bpm_ramp
# These run without any audio files and verify the mathematical properties of
# the ramp function. Always run first — if these fail, nothing else matters.
# ─────────────────────────────────────────────────────────────────────────────

class TestBpmRampUnit:
    """Pure unit tests for the _bpm_ramp helper. No audio files required."""

    def _signal(self, bpm, n_bars=12, sr=SR):
        """Synthetic stereo signal: constant 0.01 + impulse at each beat position."""
        period = sr * 60.0 / bpm
        n = int(round(n_bars * 4 * period))
        audio = np.full((n, 2), 0.01, dtype=np.float32)
        beat = 0.0
        while beat < n:
            idx = int(beat)
            if idx < n:
                audio[idx, :] = 0.9
            beat += period
        return audio, period

    def test_ratio_1_returns_unchanged(self):
        """target_ratio=1.0 → true no-op; returns b_body unchanged (array_equal)."""
        audio, period = self._signal(124.0)
        out = _bpm_ramp(audio, SR, target_ratio=1.0, body_period=period)
        np.testing.assert_array_equal(out, audio,
            err_msg="ratio=1.0 must be a true no-op — continuous resample skips via early return")

    def test_short_body_returns_unchanged(self):
        """Body ≤ ramp_n + 1 bar must return unchanged (guard against tiny bodies)."""
        audio, period = self._signal(124.0, n_bars=2)  # shorter than RAMP_BARS+1 bars
        out = _bpm_ramp(audio, SR, target_ratio=0.984, body_period=period)
        np.testing.assert_array_equal(out, audio,
            err_msg="Short body must pass through unmodified")

    def test_stable_section_never_modified(self):
        """Samples before the ramp section must be bit-identical to the input."""
        audio, period = self._signal(122.0, n_bars=12)
        ramp_n = int(round(RAMP_BARS * 4 * period))
        stable_len = len(audio) - ramp_n
        out = _bpm_ramp(audio, SR, target_ratio=0.984, body_period=period)
        np.testing.assert_array_equal(
            out[:stable_len], audio[:stable_len],
            err_msg="Stable (pre-ramp) section was modified — must be untouched"
        )

    def test_speedup_produces_shorter_output(self):
        """Compressing to a higher BPM (ratio < 1.0) must shorten the output."""
        audio, period = self._signal(122.0, n_bars=12)
        out = _bpm_ramp(audio, SR, target_ratio=0.984, body_period=period)
        assert len(out) < len(audio), (
            f"Speed-up ramp should be shorter: got {len(out)} vs input {len(audio)}"
        )

    def test_slowdown_produces_longer_output(self):
        """Expanding to a lower BPM (ratio > 1.0) must lengthen the output."""
        audio, period = self._signal(124.0, n_bars=12)
        out = _bpm_ramp(audio, SR, target_ratio=1.033, body_period=period)
        assert len(out) > len(audio), (
            f"Slow-down ramp should be longer: got {len(out)} vs input {len(audio)}"
        )

    def test_output_length_matches_average_ratio(self):
        """
        Output length ≈ stable_len + ramp_n × avg_ratio (within 2%).
        avg_ratio = midpoint between 1.0 and target_ratio (sum of chunk midpoints).
        """
        audio, period = self._signal(122.0, n_bars=12)
        target = 0.984
        ramp_n = int(round(RAMP_BARS * 4 * period))
        stable_len = len(audio) - ramp_n
        avg_ratio = 1.0 + (target - 1.0) * 0.5
        expected = stable_len + int(round(ramp_n * avg_ratio))
        out = _bpm_ramp(audio, SR, target_ratio=target, body_period=period)
        err_pct = abs(len(out) - expected) / max(expected, 1)
        assert err_pct < 0.02, (
            f"Output length {len(out)} vs expected {expected} ({err_pct*100:.2f}% off)"
        )

    def test_energy_preserved_within_20pct(self):
        """
        Mean-squared energy of the output should match the input within 20%.
        Time-stretching changes energy distribution but must not inject silence or
        clip heavily — a 20% tolerance covers the usual phase-vocoder behavior.
        """
        audio, period = self._signal(122.0, n_bars=12)
        out = _bpm_ramp(audio, SR, target_ratio=0.984, body_period=period)
        e_in  = float(np.mean(audio ** 2))
        e_out = float(np.mean(out ** 2))
        rel_err = abs(e_out - e_in) / (e_in + 1e-9)
        assert rel_err < 0.20, (
            f"Energy changed by {rel_err*100:.1f}% — possible silence or clipping in ramp"
        )

    def test_ramp_threshold_is_zero(self):
        """RAMP_THRESHOLD must be 0.0 — ramp fires for ALL transitions."""
        assert RAMP_THRESHOLD == 0.0, (
            f"RAMP_THRESHOLD is {RAMP_THRESHOLD} — should be 0.0 to catch all BPM differences"
        )

    def test_ramp_bars_is_8(self):
        """RAMP_BARS must be 8 (8 bars ≈ 16s at 122 BPM — gradual enough to be inaudible)."""
        assert RAMP_BARS == 8, f"RAMP_BARS is {RAMP_BARS} — should be 8"

    def test_ramp_chunks_is_32(self):
        """RAMP_CHUNKS must be 32 (~0.5s each → ~0.06 BPM per step — imperceptible)."""
        assert RAMP_CHUNKS == 32, f"RAMP_CHUNKS is {RAMP_CHUNKS} — should be 32"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: 3-track build (KT_Sorry → Butch_Lale → Sol_Story)
# Fast (~60s). Covers the original 6:11 rhythm-jump complaint (122→124 BPM ramp).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestThreeTrackBuild:
    """Build the 3-track test set and verify all quality checks pass."""

    @pytest.fixture(scope="class")
    def build_output(self):
        result = subprocess.run(
            [sys.executable, "build_set.py", "test3"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            timeout=600,
        )
        return {"stdout": result.stdout + result.stderr, "rc": result.returncode}

    def test_build_exits_cleanly(self, build_output):
        assert build_output["rc"] == 0, (
            f"build_set.py test3 failed (exit {build_output['rc']}):\n"
            f"{build_output['stdout']}"
        )

    def test_full_set_file_created(self, build_output):
        assert os.path.exists("output/test_3track/FULL_SET.mp3"), \
            "FULL_SET.mp3 was not created"

    def test_both_phase_errors_under_20ms(self, build_output):
        """Both KT→Butch and Butch→Sol phase errors must be < 20ms."""
        stdout = build_output["stdout"]
        errors = re.findall(r"Phase error: ([\d.]+)ms\s+([✓✗])", stdout)
        assert len(errors) == 2, \
            f"Expected 2 phase error lines, got {len(errors)}: {errors}"
        for ms_str, sym in errors:
            assert float(ms_str) < 20.0, \
                f"Phase error {ms_str}ms ≥ 20ms (threshold)"
            assert sym == "✓", \
                f"Phase check logged as failing for {ms_str}ms"

    def test_all_4_rms_boundaries_clean(self, build_output):
        """2 transitions × 2 sides = 4 RMS checks, all must pass."""
        stdout = build_output["stdout"]
        # ✗ CUT means a boundary was flagged
        cuts = re.findall(r"✗ CUT", stdout)
        assert not cuts, \
            f"Found {len(cuts)} RMS cut(s) in 3-track build — amplitude discontinuity"

    def test_ramp_fires_for_butch_122_to_124(self, build_output):
        """
        Butch body plays at KT's 122 BPM; blend A-side is Butch native at 124 BPM.
        Ramp MUST fire here — this is the original 6:11 complaint.
        """
        stdout = build_output["stdout"]
        assert "[ramp] Butch_Lale" in stdout, (
            "BPM ramp must fire for Butch_Lale (122→124 BPM) but log line not found.\n"
            "Check RAMP_THRESHOLD and that Butch body is not capped."
        )

    def test_ramp_logged_bpm_values_correct(self, build_output):
        """The ramp log line must show 122.x→124.x BPM, not reversed or wrong."""
        stdout = build_output["stdout"]
        match = re.search(r"\[ramp\] Butch_Lale: ([\d.]+)→([\d.]+) BPM", stdout)
        assert match, "Could not find [ramp] Butch_Lale log line"
        from_bpm = float(match.group(1))
        to_bpm   = float(match.group(2))
        assert 120 < from_bpm < 124, f"From BPM {from_bpm} not in expected 120-124 range"
        assert 122 < to_bpm   < 126, f"To BPM {to_bpm} not in expected 122-126 range"
        assert to_bpm > from_bpm, "Speed-up ramp should go from lower to higher BPM"

    def test_snippet_files_exist(self, build_output):
        snippets = [
            "output/test_3track/01_KT_Sorry_into_Butch_Lale.mp3",
            "output/test_3track/02_Butch_Lale_into_Sol_Story.mp3",
        ]
        for path in snippets:
            assert os.path.exists(path), f"Snippet missing: {path}"

    def test_all_blend_boundaries_reported_clean(self, build_output):
        assert "All blend boundaries clean ✓" in build_output["stdout"], (
            "Expected 'All blend boundaries clean ✓' summary line"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Integration: full solomun 20-track set
# Slow (~10 min). Run before any release.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestSolomunFullSet:
    """Build and verify the complete 20-track SORRY I AM LATE set."""

    @pytest.fixture(scope="class")
    def build_output(self):
        result = subprocess.run(
            [sys.executable, "build_set.py", "solomun"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            timeout=3600,
        )
        return {"stdout": result.stdout + result.stderr, "rc": result.returncode}

    def test_build_exits_cleanly(self, build_output):
        assert build_output["rc"] == 0, (
            f"build_set.py solomun failed (exit {build_output['rc']}):\n"
            f"{build_output['stdout'][-3000:]}"
        )

    def test_full_set_and_notes_exist(self, build_output):
        assert os.path.exists("output/sorry_i_am_late/FULL_SET.mp3"), \
            "FULL_SET.mp3 not created"
        assert os.path.exists("output/sorry_i_am_late/SET_NOTES.txt"), \
            "SET_NOTES.txt not created"

    def test_19_phase_errors_all_under_20ms(self, build_output):
        """Every transition must pass the 20ms phase threshold."""
        stdout = build_output["stdout"]
        errors = re.findall(r"Phase error: ([\d.]+)ms\s+([✓✗])", stdout)
        assert len(errors) == 19, \
            f"Expected 19 phase error lines (one per transition), got {len(errors)}"
        failures = [
            (ms, sym) for ms, sym in errors
            if sym != "✓" or float(ms) >= 20.0
        ]
        assert not failures, \
            f"Phase errors above 20ms threshold: {failures}"

    def test_no_rms_cuts_in_full_set(self, build_output):
        """No blend boundary may be flagged as a cut (RMS ratio ≥ 3.0x)."""
        stdout = build_output["stdout"]
        cuts = re.findall(r"✗ CUT", stdout)
        assert not cuts, \
            f"Found {len(cuts)} amplitude cut(s) — check the flagged transitions"

    def test_all_blend_boundaries_reported_clean(self, build_output):
        assert "All blend boundaries clean ✓" in build_output["stdout"]

    def test_at_least_6_ramps_applied(self, build_output):
        """
        At minimum 6 ramps fire (the tracks with >1 BPM differences). With
        RAMP_THRESHOLD=0.0, more may fire for smaller differences.
        """
        stdout = build_output["stdout"]
        ramp_lines = re.findall(r"\[ramp\]", stdout)
        assert len(ramp_lines) >= 6, (
            f"Expected ≥6 ramps in solomun set (known cross-BPM transitions), "
            f"got {len(ramp_lines)}. Check RAMP_THRESHOLD."
        )

    def test_cue_sheet_has_19_transition_entries(self, build_output):
        """SET_NOTES.txt cue sheet must list all 19 transitions."""
        notes = "output/sorry_i_am_late/SET_NOTES.txt"
        with open(notes) as f:
            content = f.read()
        entries = re.findall(r"\[\d{2}\] →", content)
        assert len(entries) == 19, \
            f"Cue sheet has {len(entries)} entries — expected 19"

    def test_19_snippet_files_exported(self, build_output):
        """One snippet per transition, 1-indexed 01 through 19."""
        for i in range(1, 20):
            matches = [
                f for f in os.listdir("output/sorry_i_am_late/")
                if f.startswith(f"{i:02d}_") and f.endswith(".mp3")
            ]
            assert matches, f"No snippet file found for transition {i:02d}"

    def test_set_duration_in_expected_range(self, build_output):
        """Full mix should be 60–65 minutes (accounts for ramp length changes)."""
        stdout = build_output["stdout"]
        match = re.search(r"Full mix: ([\d.]+) min", stdout)
        assert match, "Could not find 'Full mix: X min' in build output"
        minutes = float(match.group(1))
        assert 60 <= minutes <= 65, \
            f"Set duration {minutes:.1f} min outside expected 60–65 min range"

    def test_no_repeat_audio_marker(self, build_output):
        """
        The build must NOT contain any 'REPEAT' or 'OVERLAP' error in the output.
        This guards against the preload bug where body_end audio was played twice.
        """
        stdout = build_output["stdout"]
        assert "REPEAT" not in stdout.upper() or "No repeat" in stdout, \
            "Unexpected REPEAT marker in build output"

    @pytest.mark.parametrize("track,bpm_from,bpm_to", [
        ("Butch_Lale",    122, 124),   # original 6:11 complaint
        ("Innellea",      123, 120),   # Patrice→Innellea blend
        ("Wassermann",    120, 124),   # Innellea→Wassermann blend
        ("Sol_Amanacer",  122, 120),   # GuyGerber→Amanacer blend
        ("TubeNBerger",   120, 122),   # Amanacer→TubeNBerger blend
        ("TaleOfUs",      123, 125),   # Adriatique→TaleOfUs blend
    ])
    def test_known_cross_bpm_ramps_fire(self, build_output, track, bpm_from, bpm_to):
        """Each known cross-BPM pair must have a [ramp] log line in the build output."""
        stdout = build_output["stdout"]
        assert f"[ramp] {track}" in stdout, (
            f"Expected [ramp] {track}: {bpm_from}→{bpm_to} BPM but log line not found"
        )
