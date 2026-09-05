#!/usr/bin/env python3
"""
Warn when the packaged Mac/Windows app source copies (mac_app/djbot_src/,
windows_app/djbot_src/) have drifted from the real source (mixer/, webapp/,
make_mix.py, requirements.txt).

Why this exists (confirmed live 2026-09-04): mac_app/djbot_src/ is a
separate, manually-synced copy — the actual installed app runs from it, not
from the live repo. It was found to be dated Aug 19, 2026: before the Aug 22
AppleScript-injection fix, before the entire Aug 28 harmonic-mixing branch,
and before the hard-cut BPM-ramp bug fix from this same session. That drift
was silent — nothing flagged it until a live Surprise Me run was traced by
hand. This script makes that check cheap and repeatable instead of relying
on remembering to check.

Extended 2026-09-05 to also cover windows_app/djbot_src/ — same structure
(mixer/, webapp/, make_mix.py, requirements.txt; windows_app just lacks the
empty downloads/output/ dirs, which aren't compared anyway), had never been
checked at all until now.

Usage:
  python mac_app/check_stale.py              # checks both mac and windows
  python mac_app/check_stale.py --target mac
  python mac_app/check_stale.py --target windows

Exit code 0 = every checked target is in sync. Exit code 1 = drift found in
at least one target (differing and/or entirely-missing files listed). Safe
to wire into CI later; today it's a manual pre-flight check before
mac_app/build_signed_app.sh (Windows has no equivalent build script yet).

Does not compare downloads/ or output/ (the app-building steps already
exclude those from the packaged copy on purpose — job data, not source).
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    "mac": ROOT / "mac_app" / "djbot_src",
    "windows": ROOT / "windows_app" / "djbot_src",
}

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


def check(label: str, djbot_src: Path) -> int:
    differing = []
    missing = []
    matched = 0

    for rel_path in _iter_source_files():
        source_path = ROOT / rel_path
        packaged_path = djbot_src / rel_path
        if not packaged_path.is_file():
            missing.append(rel_path)
            continue
        if _sha256(source_path) != _sha256(packaged_path):
            differing.append(rel_path)
        else:
            matched += 1

    print(f"\n  Checking {djbot_src.relative_to(ROOT)}/ against source ({ROOT})\n")

    if missing:
        print(f"  MISSING from {label} djbot_src ({len(missing)}) — not packaged at all:")
        for p in missing:
            print(f"    {p}")
        print()

    if differing:
        print(f"  DIFFERS from source ({len(differing)}) — {label} packaged copy is stale:")
        for p in differing:
            print(f"    {p}")
        print()

    print(f"  {matched} file(s) match, {len(differing)} differ, "
          f"{len(missing)} missing entirely.\n")

    if differing or missing:
        print(f"  {label} djbot_src is STALE — re-sync before building.\n")
        return 1
    print(f"  {label} djbot_src is in sync with source. ✓\n")
    return 0


def main() -> int:
    target = None
    if "--target" in sys.argv:
        target = sys.argv[sys.argv.index("--target") + 1]
        if target not in TARGETS:
            print(f"Unknown target {target!r} — choose from {list(TARGETS)}")
            return 2

    to_check = {target: TARGETS[target]} if target else TARGETS
    worst = 0
    for label, djbot_src in to_check.items():
        worst = max(worst, check(label, djbot_src))
    return worst


if __name__ == "__main__":
    sys.exit(main())
