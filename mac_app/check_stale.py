#!/usr/bin/env python3
"""
Warn when the packaged Mac app's source copy (mac_app/djbot_src/) has
drifted from the real source (mixer/, webapp/, make_mix.py, requirements.txt).

Why this exists (confirmed live 2026-09-04): mac_app/djbot_src/ is a
separate, manually-synced copy — the actual installed app runs from it, not
from the live repo. It was found to be dated Aug 19, 2026: before the Aug 22
AppleScript-injection fix, before the entire Aug 28 harmonic-mixing branch,
and before the hard-cut BPM-ramp bug fix from this same session. That drift
was silent — nothing flagged it until a live Surprise Me run was traced by
hand. This script makes that check cheap and repeatable instead of relying
on remembering to check.

Usage:
  python mac_app/check_stale.py

Exit code 0 = djbot_src is in sync. Exit code 1 = drift found (differing
and/or entirely-missing files listed). Safe to wire into CI later; today
it's a manual pre-flight check before `mac_app/build_signed_app.sh`.

Does not compare downloads/ or output/ (build_signed_app.sh already
excludes those from the packaged copy on purpose — job data, not source).
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DJBOT_SRC = ROOT / "mac_app" / "djbot_src"

# Directories compared recursively; single files compared directly.
DIRS_TO_CHECK = ["mixer", "webapp"]
FILES_TO_CHECK = ["make_mix.py", "requirements.txt"]

SKIP_SUFFIXES = (".pyc",)
SKIP_DIR_NAMES = {"__pycache__"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _iter_source_files():
    for dirname in DIRS_TO_CHECK:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_dir():
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            if SKIP_DIR_NAMES & set(path.relative_to(ROOT).parts):
                continue
            yield path.relative_to(ROOT)
    for fname in FILES_TO_CHECK:
        path = ROOT / fname
        if path.is_file():
            yield path.relative_to(ROOT)


def check() -> int:
    differing = []
    missing = []
    matched = 0

    for rel_path in _iter_source_files():
        source_path = ROOT / rel_path
        packaged_path = DJBOT_SRC / rel_path
        if not packaged_path.is_file():
            missing.append(rel_path)
            continue
        if _sha256(source_path) != _sha256(packaged_path):
            differing.append(rel_path)
        else:
            matched += 1

    print(f"\n  Checking mac_app/djbot_src/ against source ({ROOT})\n")

    if missing:
        print(f"  MISSING from djbot_src ({len(missing)}) — not packaged at all:")
        for p in missing:
            print(f"    {p}")
        print()

    if differing:
        print(f"  DIFFERS from source ({len(differing)}) — packaged copy is stale:")
        for p in differing:
            print(f"    {p}")
        print()

    print(f"  {matched} file(s) match, {len(differing)} differ, "
          f"{len(missing)} missing entirely.\n")

    if differing or missing:
        print("  djbot_src is STALE — re-sync before running mac_app/build_signed_app.sh.\n")
        return 1
    print("  djbot_src is in sync with source. ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(check())
