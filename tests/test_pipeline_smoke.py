"""
Pipeline smoke tests — verify the Railway worker can:
  1. Import all pipeline modules without error
  2. Style selector returns a valid brain name
  3. Quality gate correctly passes/fails on synthetic notes
  4. Worker can be invoked as a module (--help exits 0)

These run without audio files (~1s) and are safe to run on Railway at deploy time.
Mark slow integration tests with @pytest.mark.slow — they require audio files.
"""

import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ── Module import checks ───────────────────────────────────────────────────────

def test_pipeline_imports():
    for module in ["pipeline.worker", "pipeline.style_selector", "pipeline.quality_gate"]:
        importlib.import_module(module)


def test_all_brain_modules_import():
    brains_dir = Path(__file__).parent.parent / "brains"
    for f in sorted(brains_dir.glob("*.py")):
        if f.stem.startswith("_") or f.stem == "test3":
            continue
        mod = importlib.import_module(f"brains.{f.stem}")
        assert hasattr(mod, "TRACKS"), f"brains/{f.stem}.py missing TRACKS"
        assert hasattr(mod, "SET_NAME"), f"brains/{f.stem}.py missing SET_NAME"
        assert len(mod.TRACKS) >= 2, f"brains/{f.stem}.py has fewer than 2 tracks"


# ── Style selector ─────────────────────────────────────────────────────────────

def test_style_selector_returns_valid_brain():
    from pipeline.style_selector import current_brain, ROTATION
    brain = current_brain()
    assert brain in ROTATION, f"current_brain() returned {brain!r} not in ROTATION"


def test_style_selector_override(monkeypatch):
    monkeypatch.setenv("DJKYOKO_BRAIN", "solomun")
    from pipeline import style_selector
    importlib.reload(style_selector)
    assert style_selector.current_brain() == "solomun"


# ── Quality gate ───────────────────────────────────────────────────────────────

GOOD_NOTES = textwrap.dedent("""\
    TrackA → TrackB 5.2ms ✓
    TrackB → TrackC 8.1ms ✓
    blend-in  A→B  RMS ratio 1.23 ✓
    blend-out A→B  RMS ratio 1.45 ✓
    blend-in  B→C  RMS ratio 2.10 ✓
    blend-out B→C  RMS ratio 1.80 ✓
""")

BAD_NOTES_PHASE = textwrap.dedent("""\
    TrackA → TrackB 5.2ms ✓
    TrackB → TrackC 28.4ms ✗
    blend-in  A→B  RMS ratio 1.23 ✓
""")

BAD_NOTES_RMS = textwrap.dedent("""\
    TrackA → TrackB 5.2ms ✓
    blend-in  A→B  RMS ratio 4.55 ✗
""")


@pytest.fixture
def fake_set(tmp_path):
    """Create a minimal set directory for quality gate tests."""
    mp3 = tmp_path / "FULL_SET.mp3"
    mp3.write_bytes(b"\x00" * (21 * 1024 * 1024))   # 21 MB fake mp3
    return tmp_path


def test_quality_gate_passes(fake_set):
    (fake_set / "SET_NOTES.txt").write_text(GOOD_NOTES)
    from pipeline.quality_gate import check
    passed, report = check(fake_set)
    assert passed, f"Expected pass:\n{report}"
    assert "PASS" in report


def test_quality_gate_fails_on_high_phase(fake_set):
    (fake_set / "SET_NOTES.txt").write_text(BAD_NOTES_PHASE)
    from pipeline.quality_gate import check
    passed, report = check(fake_set)
    assert not passed, f"Expected fail on 28ms phase error:\n{report}"
    assert "FAIL" in report


def test_quality_gate_fails_on_high_rms(fake_set):
    (fake_set / "SET_NOTES.txt").write_text(BAD_NOTES_RMS)
    from pipeline.quality_gate import check
    passed, report = check(fake_set)
    assert not passed, f"Expected fail on 4.55x RMS ratio:\n{report}"


def test_quality_gate_fails_missing_mp3(tmp_path):
    (tmp_path / "SET_NOTES.txt").write_text(GOOD_NOTES)
    from pipeline.quality_gate import check
    passed, _ = check(tmp_path)
    assert not passed


def test_quality_gate_fails_small_mp3(fake_set):
    small_mp3 = fake_set / "FULL_SET.mp3"
    small_mp3.write_bytes(b"\x00" * (5 * 1024 * 1024))   # 5 MB — too small
    (fake_set / "SET_NOTES.txt").write_text(GOOD_NOTES)
    from pipeline.quality_gate import check
    passed, report = check(fake_set)
    assert not passed
    assert "MB" in report


# ── Worker CLI ─────────────────────────────────────────────────────────────────

def test_worker_help():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.worker", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0
    assert "--brain" in result.stdout
    assert "--dry-run" in result.stdout
