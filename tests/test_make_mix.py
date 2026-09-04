"""Unit tests for make_mix.py's harmonic re-sort (2026-09-04)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from make_mix import _harmonic_resort


def _t(name):
    return {"path": name, "name": name}


def _g(bpm, camelot, low_conf=False):
    return {"bpm": bpm, "camelot": camelot, "key_low_confidence": low_conf}


def test_no_change_when_already_compatible():
    tracks = [_t("A"), _t("B"), _t("C")]
    grids = [_g(120, "8A"), _g(121, "8A"), _g(122, "8A")]
    out = _harmonic_resort(tracks, grids)
    assert [t["path"] for t in out] == ["A", "B", "C"]


def test_swaps_in_compatible_track_from_later_in_list():
    # B (3B) clashes with A (8A) — different letter, non-adjacent number.
    # D (8A) is compatible (identical code) and same tempo tier as A —
    # should get pulled forward to position 1, bumping B and C back.
    tracks = [_t("A"), _t("B"), _t("C"), _t("D")]
    grids = [_g(120, "8A"), _g(121, "3B"), _g(122, "6B"), _g(120, "8A")]
    out = _harmonic_resort(tracks, grids)
    assert [t["path"] for t in out] == ["A", "D", "C", "B"]


def test_never_reorders_across_a_big_tempo_jump():
    # A->B is incompatible (8A vs 3B) AND already a huge tempo jump (well
    # past 15%) — leave it alone even though C would be compatible with A.
    tracks = [_t("A"), _t("B"), _t("C")]
    grids = [_g(90, "8A"), _g(150, "3B"), _g(90, "8A")]
    out = _harmonic_resort(tracks, grids)
    assert [t["path"] for t in out] == ["A", "B", "C"]


def test_never_trusts_low_confidence_keys():
    tracks = [_t("A"), _t("B"), _t("C")]
    grids = [_g(120, "8A"), _g(121, "3B", low_conf=True), _g(122, "8A")]
    out = _harmonic_resort(tracks, grids)
    assert [t["path"] for t in out] == ["A", "B", "C"]


def test_preserves_all_tracks_no_drop_no_duplicate():
    tracks = [_t("A"), _t("B"), _t("C"), _t("D"), _t("E")]
    grids = [_g(120, "8A"), _g(121, "3B"), _g(122, "6B"), _g(120, "8A"), _g(123, "9A")]
    out = _harmonic_resort(tracks, grids)
    assert sorted(t["path"] for t in out) == ["A", "B", "C", "D", "E"]


def test_missing_bpm_is_skipped_safely():
    tracks = [_t("A"), _t("B")]
    grids = [_g(None, "8A"), _g(121, "9A")]
    out = _harmonic_resort(tracks, grids)
    assert [t["path"] for t in out] == ["A", "B"]
