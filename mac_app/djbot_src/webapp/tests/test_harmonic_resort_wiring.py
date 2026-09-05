"""Unit tests for job_runner.py's _apply_harmonic_resort (2026-09-05).

make_mix.py's _harmonic_resort itself already has 6 tests
(tests/test_make_mix.py) covering the swap/tempo-jump-guard/low-confidence
behavior. This file covers the wiring on top of it that's specific to
job_runner.py: renaming tracks to match their new position, keeping
tracks_state in sync with build_tracks, and never losing a failed-download
track that was never part of build_tracks in the first place.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_runner import _apply_harmonic_resort


def _bt(name, path):
    return {"name": name, "label": path, "path": path, "hint": 120}


def _ts(name, label=None, download_status="done"):
    return {"name": name, "label": label or name, "bpm": 120,
            "download_status": download_status, "download_pct": 100}


def _g(bpm, camelot, low_conf=False):
    return {"bpm": bpm, "camelot": camelot, "key_low_confidence": low_conf}


def test_no_resort_leaves_everything_unchanged():
    build_tracks = [_bt("T01", "A"), _bt("T02", "B")]
    tracks_state = [_ts("T01"), _ts("T02")]
    grids = [_g(120, "8A"), _g(121, "8A")]  # already compatible
    bt, ts = _apply_harmonic_resort(build_tracks, tracks_state, grids)
    assert bt is build_tracks
    assert ts is tracks_state


def test_resort_renames_and_reorders_both_lists_together():
    # B (3B) clashes with A (8A); D (8A) is compatible and same tempo tier.
    build_tracks = [_bt("T01", "A"), _bt("T02", "B"), _bt("T03", "C"), _bt("T04", "D")]
    tracks_state = [_ts("T01", "A"), _ts("T02", "B"), _ts("T03", "C"), _ts("T04", "D")]
    grids = [_g(120, "8A"), _g(121, "3B"), _g(122, "6B"), _g(120, "8A")]

    bt, ts = _apply_harmonic_resort(build_tracks, tracks_state, grids)

    assert [t["path"] for t in bt] == ["A", "D", "C", "B"]
    assert [t["name"] for t in bt] == ["T01", "T02", "T03", "T04"]
    # tracks_state must mirror build_tracks exactly — same order, same names.
    assert [s["label"] for s in ts] == ["A", "D", "C", "B"]
    assert [s["name"] for s in ts] == ["T01", "T02", "T03", "T04"]


def test_failed_download_tracks_are_preserved_and_appended_after():
    # Only A and C actually made it into build_tracks/grids (B failed to
    # download and was skipped before this function is ever called).
    build_tracks = [_bt("T01", "A"), _bt("T03", "C")]
    tracks_state = [_ts("T01", "A"), _ts("T02", "B", download_status="failed"), _ts("T03", "C")]
    grids = [_g(120, "8A"), _g(150, "3B")]  # huge tempo jump — resort won't touch it

    bt, ts = _apply_harmonic_resort(build_tracks, tracks_state, grids)

    # No resort fires (tempo jump too big) — nothing should change at all,
    # failed track included.
    assert bt is build_tracks
    assert ts is tracks_state


def test_failed_download_track_survives_a_real_resort_with_no_name_collision():
    # Regression test: originally, a failed track kept its untouched
    # original name while successfully-built tracks were renamed
    # sequentially from T01 — if the failed track's original position
    # collided with a newly-assigned name (both "T03" here), two entries
    # in tracks_state ended up with the same "name". Fixed by renumbering
    # failed tracks to continue the sequence after the built ones.
    build_tracks = [_bt("T01", "A"), _bt("T02", "B"), _bt("T04", "D")]
    tracks_state = [_ts("T01", "A"), _ts("T02", "B"),
                     _ts("T03", "FAILED", download_status="failed"), _ts("T04", "D")]
    grids = [_g(120, "8A"), _g(121, "3B"), _g(120, "8A")]

    bt, ts = _apply_harmonic_resort(build_tracks, tracks_state, grids)

    assert [t["path"] for t in bt] == ["A", "D", "B"]
    labels = [s["label"] for s in ts]
    assert labels == ["A", "D", "B", "FAILED"]
    names = [s["name"] for s in ts]
    assert names == ["T01", "T02", "T03", "T04"]
    assert len(names) == len(set(names)), f"duplicate track name(s): {names}"
    assert any(s["download_status"] == "failed" for s in ts)
