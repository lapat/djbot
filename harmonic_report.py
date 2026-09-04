"""
Harmonic (Camelot Wheel) curation report — entry point.

Usage:
  python harmonic_report.py solomun
  python harmonic_report.py solomun --set-order   # also suggest a reorder

Prints each consecutive track pair in a brain's TRACKS list with its BPM
diff_pct, detected Camelot keys, and whether they're harmonically compatible
(mixer/harmonic.py's camelot_compatible()) — a curation aid for hand-ordering
a set, same spirit as a DJ checking the Camelot wheel while building a set.

This is a diagnostic tool, not an automatic set-orderer: djbot's brains are
hand-curated TRACKS lists (see brains/*.py), not an algorithm that orders
tracks on its own, so there's no automatic ordering step to "wire" harmonic
compatibility into (scoped 2026-08-28's original framing assumed one exists —
it doesn't; this report is the honest alternative). Run it before or after
hand-ordering a tracklist to see where the curation already lines up
harmonically and where it doesn't — key compatibility is one more signal
alongside BPM flow and energy arc, not a replacement for either.

Requires each track's beat grid (and now key) to already be analyzed/cached
in downloads/library/beatgrid_cache.json, or it will analyze (and cache) them
now — same as a normal build.
"""
import sys, os, importlib

sys.path.insert(0, os.path.dirname(__file__))
from mixer.beatgrid import get_or_analyze
from mixer.harmonic import camelot_compatible
from make_mix import _harmonic_resort

AVAILABLE = ["luno", "solomun", "afterlife", "test3",
             "taleous", "bodzin", "bicep", "maceoplex", "benbohmer"]


def _analyze_all(tracks):
    return [get_or_analyze(t["path"], hint_bpm=t["hint"]) for t in tracks]


def report(brain, grids=None):
    tracks = brain.TRACKS
    print(f"\n  Harmonic report: {brain.SET_NAME}  ({len(tracks)} tracks)\n")

    if grids is None:
        grids = _analyze_all(tracks)

    compatible_count = 0
    for i, t in enumerate(tracks):
        g = grids[i]
        camelot = g.get("camelot", "?")
        key_flag = " (low-conf)" if g.get("key_low_confidence") else ""
        line = f"  {i+1:02d}  {t['label']:<40} {camelot:>4}{key_flag}  {g['bpm']:.1f} BPM"

        if i > 0:
            prev_g = grids[i - 1]
            diff_pct = abs(prev_g["bpm"] - g["bpm"]) / prev_g["bpm"] * 100
            compatible = camelot_compatible(prev_g.get("camelot"), g.get("camelot"))
            if compatible:
                compatible_count += 1
            sym = "✓ compatible" if compatible else "· clash"
            line += f"    [{diff_pct:5.1f}% BPM gap from prev, key {sym}]"

        print(line)

    n_transitions = len(tracks) - 1
    if n_transitions > 0:
        pct = 100 * compatible_count / n_transitions
        print(f"\n  {compatible_count}/{n_transitions} transitions ({pct:.0f}%) are "
              f"harmonically compatible by Camelot adjacency.\n")


def suggest_set_order(brain, grids):
    """
    Print-only: what mixer.harmonic + make_mix's soft re-sort would suggest
    for this brain's TRACKS list. Never writes anything — brains stay
    hand-curated by design (see this file's module docstring). Reuses
    make_mix.py's _harmonic_resort (2026-09-04) rather than a second
    implementation, so the diagnostic always matches what an actual
    make_mix.py free-text build would do with the same tracks.
    """
    tracks = brain.TRACKS
    max_diff = getattr(brain, "MAX_BPM_DIFF_PCT", 8.0)
    resorted = _harmonic_resort(tracks, grids, max_bpm_diff_pct=max_diff)

    print(f"  Suggested set order (max_bpm_diff_pct={max_diff}):\n")
    if [t["path"] for t in resorted] == [t["path"] for t in tracks]:
        print("  No change — current order already respects harmonic "
              "compatibility within tempo-compatible neighbors.\n")
        return

    orig_index = {id(t): i for i, t in enumerate(tracks)}
    for new_pos, t in enumerate(resorted):
        old_pos = orig_index[id(t)]
        moved = "" if old_pos == new_pos else f"  (was #{old_pos + 1:02d})"
        print(f"  {new_pos + 1:02d}  {t['label']:<40}{moved}")
    print("\n  This is a suggestion only — brains/*.py stays hand-curated; "
          "nothing was written.\n")


def main():
    args = sys.argv[1:]
    set_order = "--set-order" in args
    positional = [a for a in args if not a.startswith("--")]

    if len(positional) < 1 or positional[0] not in AVAILABLE:
        print(f"\nUsage: python harmonic_report.py [{' | '.join(AVAILABLE)}] [--set-order]\n")
        sys.exit(1)

    brain = importlib.import_module(f"brains.{positional[0]}")
    grids = _analyze_all(brain.TRACKS)
    report(brain, grids=grids)
    if set_order:
        suggest_set_order(brain, grids)


if __name__ == "__main__":
    main()
