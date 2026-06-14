#!/usr/bin/env python3
"""
Pre-analyze all tracks in the library — run this ONCE before mixing.
Stores: BPM (precise), beat_anchor_sample, sr into beatgrid_cache.json.
Mixing then needs zero beat detection — pure arithmetic.

Usage:
    python preanalyze.py            # analyze all cached tracks
    python preanalyze.py --force    # re-analyze everything
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from mixer.beatgrid import get_or_analyze

TRACK_CACHE = "downloads/library/track_cache.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-analyze even if cached")
    args = parser.parse_args()

    with open(TRACK_CACHE) as f:
        tracks = json.load(f)

    print(f"Pre-analyzing {len(tracks)} tracks...\n")
    for key, t in tracks.items():
        path = t.get("path", "")
        if not os.path.exists(path):
            print(f"  SKIP (missing): {path}")
            continue

        hint_bpm = t.get("bpm", 120.0)
        print(f"[{t.get('artist','')} - {t.get('title','')}]")
        grid = get_or_analyze(path, hint_bpm=hint_bpm, force=args.force)
        print(f"  BPM={grid['bpm']:.4f}  anchor={grid['beat_anchor_sample']} samp  sr={grid['sr']}")
        print()

    print("Done. Beat grids stored in downloads/library/beatgrid_cache.json")

if __name__ == "__main__":
    main()
