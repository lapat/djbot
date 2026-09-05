#!/usr/bin/env python3
"""
One-off: recover beatgrid_cache.json entries stranded by the project's
Desktop/vibe/djbot -> vibe/djbot directory move.

get_or_analyze() keys the cache by absolute path (mixer/beatgrid.py:
"Key = absolute path so the cache survives working-directory changes" —
true only for a rename of the working directory that leaves the abs path
stable, which is exactly what broke here). Every entry analyzed before the
move is keyed under the OLD prefix and gets zero cache hits under the new
one, silently forcing a full re-analysis on the next real build.

This rewrites old-prefixed keys to the new prefix ONLY where the file still
exists at the new path (never invents a mapping) and never overwrites an
entry that's already cached under the new-prefixed key (the newer analysis,
if one exists, wins).

Usage:
  python scripts/migrate_beatgrid_cache_paths.py            # dry run
  python scripts/migrate_beatgrid_cache_paths.py --apply    # writes the file
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "downloads" / "library" / "beatgrid_cache.json"

OLD_PREFIX = "/Users/louislapat/Desktop/vibe/djbot/"
NEW_PREFIX = "/Users/louislapat/vibe/djbot/"


def migrate(apply: bool) -> int:
    with open(CACHE_PATH) as f:
        cache = json.load(f)

    migrated, skipped_exists, skipped_missing = 0, 0, 0
    for old_key in [k for k in cache if k.startswith(OLD_PREFIX)]:
        new_key = NEW_PREFIX + old_key[len(OLD_PREFIX):]
        if not os.path.exists(new_key):
            skipped_missing += 1
            continue
        if new_key in cache:
            skipped_exists += 1  # a newer analysis already exists — don't clobber it
            continue
        cache[new_key] = cache[old_key]
        migrated += 1

    print(f"  {migrated} entries recoverable at the new path")
    print(f"  {skipped_exists} skipped (already have a newer cache entry)")
    print(f"  {skipped_missing} skipped (file no longer exists at the new path)")

    if apply and migrated:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"  Wrote {CACHE_PATH}")
    elif migrated:
        print("  Dry run — re-run with --apply to write the migrated cache.")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))
