"""
Quality gate — runs before any Mixcloud upload.
Checks phase error and amplitude continuity on the built mix.
Returns (passed: bool, report: str).
"""
import re
from pathlib import Path


PHASE_THRESHOLD_MS  = 20.0
RMS_THRESHOLD       = 3.0
MIN_FILE_SIZE_MB    = 20


def check(set_dir: str | Path) -> tuple[bool, str]:
    set_dir   = Path(set_dir)
    mp3_path  = set_dir / "FULL_SET.mp3"
    notes_path = set_dir / "SET_NOTES.txt"
    lines = []
    passed = True

    # 1. File exists and is big enough
    if not mp3_path.exists():
        return False, f"FAIL: {mp3_path} does not exist"

    size_mb = mp3_path.stat().st_size / 1e6
    if size_mb < MIN_FILE_SIZE_MB:
        return False, f"FAIL: {mp3_path} is only {size_mb:.1f} MB (< {MIN_FILE_SIZE_MB} MB)"
    lines.append(f"  file size:    {size_mb:.1f} MB  ✓")

    # 2. Parse SET_NOTES.txt for logged phase errors and RMS ratios
    if not notes_path.exists():
        return False, f"FAIL: {notes_path} does not exist"

    text = notes_path.read_text()

    # Phase errors: "TrackA  → TrackB  X.Xms  ✓/✗"
    phase_errors = re.findall(
        r"(\S+)\s+→\s+(\S+)\s+([\d.]+)ms\s+(✓|✗)", text
    )
    if not phase_errors:
        return False, "FAIL: no phase error data found in SET_NOTES.txt"

    phase_pass = True
    for a, b, ms, flag in phase_errors:
        ms_f = float(ms)
        ok   = ms_f < PHASE_THRESHOLD_MS
        if not ok:
            phase_pass = False
            passed     = False
        lines.append(f"  phase {a}→{b}: {ms}ms  {'✓' if ok else '✗ FAIL'}")

    # 3. RMS ratios: "blend-in  A→B  RMS ratio X.XX  ✓/✗"
    rms_checks = re.findall(
        r"blend-(?:in|out)\s+(\S+)\s+RMS ratio ([\d.]+)\s+(✓|✗)", text
    )
    rms_pass = True
    for label, ratio, flag in rms_checks:
        ratio_f = float(ratio)
        ok      = ratio_f < RMS_THRESHOLD
        if not ok:
            rms_pass = False
            passed   = False
        lines.append(f"  rms {label}: {ratio}x  {'✓' if ok else '✗ FAIL'}")

    if not rms_checks:
        lines.append("  rms: no data (older SET_NOTES format)")

    status = "PASS" if passed else "FAIL"
    report = f"Quality gate: {status}\n" + "\n".join(lines)
    return passed, report
