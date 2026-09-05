"""
Harmonic (Camelot Wheel) key detection and compatibility scoring.

Scoped 2026-08-28 (SCOPING_2026-08-28.md), built 2026-08-28. djbot previously
did zero key/pitch detection — this is a genuinely new signal, additive to
(never a replacement for) the existing BPM-based tier system in
set_builder.py. Nothing here gates or blocks a build; it's a curation aid.

Key estimation: chroma pitch-class profile (librosa) correlated against the
standard Krumhansl-Kessler (1990) major/minor key profiles — the well-known
cheap approach for this task. Chroma-based key detection is noticeably less
reliable on tracks with an ambiguous/modal/drone-based tonal center (common
in techno/tech-house, which is most of what djbot mixes per the brain files)
— hence `key_low_confidence`, mirroring the existing beat-detection
low_confidence pattern in beatgrid.py: a small correlation margin between the
best and second-best key guess means the tonal center itself is ambiguous,
and the key guess should be treated as unreliable rather than trusted.
"""
from __future__ import annotations

import numpy as np

# Camelot Wheel — standard DJ harmonic-mixing notation (matches Mixed In Key
# and the notation already hand-written into brains/solomun.py's SET_NOTES,
# e.g. "2B  122 BPM"). Maps a pitch class (0=C, 1=C#, ... 11=B — matches
# librosa's chroma bin ordering, which starts at C) to its Camelot code.
CAMELOT_MAJOR = {
    0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
    6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B",
}
CAMELOT_MINOR = {
    0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
    6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A",
}

_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler (1990) key profiles — perceptual weight of each scale
# degree relative to the tonic, index 0 = tonic. Standard reference values.
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Below this correlation margin (best key guess vs. runner-up), treat the key
# as ambiguous rather than trust it. Not yet tuned against real labeled DJ
# material (no ground-truth-keyed audio was available locally to calibrate
# against) — a reasonable starting point, revisit if real detections look
# consistently over- or under-confident once run against the real library.
KEY_CONFIDENCE_MARGIN_THRESHOLD = 0.05


def detect_key(y: np.ndarray, sr: int) -> dict:
    """
    Estimate musical key from already-loaded mono audio (no separate file
    load — call with the same `y, sr` beatgrid.py's analyze_track() already
    has in memory from `_load_mono()`).

    Returns: camelot (e.g. "8B"), key_name (e.g. "C major"),
    key_confidence_margin (float), key_low_confidence (bool).
    """
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    profile = chroma.mean(axis=1)
    profile = profile / (np.linalg.norm(profile) + 1e-9)

    scores = []
    for shift in range(12):
        maj = np.roll(_KS_MAJOR, shift)
        minr = np.roll(_KS_MINOR, shift)
        maj_corr = float(np.corrcoef(profile, maj / np.linalg.norm(maj))[0, 1])
        min_corr = float(np.corrcoef(profile, minr / np.linalg.norm(minr))[0, 1])
        scores.append((maj_corr, shift, "major"))
        scores.append((min_corr, shift, "minor"))

    scores.sort(key=lambda s: s[0], reverse=True)
    best_corr, best_shift, best_mode = scores[0]
    margin = best_corr - scores[1][0]

    camelot = (CAMELOT_MAJOR if best_mode == "major" else CAMELOT_MINOR)[best_shift]
    key_name = f"{_PITCH_NAMES[best_shift]} {best_mode}"

    return {
        "camelot":               camelot,
        "key_name":              key_name,
        "key_confidence_margin": round(margin, 4),
        "key_low_confidence":    margin < KEY_CONFIDENCE_MARGIN_THRESHOLD,
    }


def camelot_compatible(code_a: str | None, code_b: str | None) -> bool:
    """
    True if two Camelot codes are harmonically compatible for a DJ
    transition: identical number (same key or relative major/minor), or
    same letter with adjacent number (wheel-adjacent, wraps 12<->1).

    A soft signal, not a hard filter — see harmonic_report.py. Curation
    priorities (energy arc, etc.) should not be overridden by key alone.
    """
    if not code_a or not code_b:
        return False
    na, la = int(code_a[:-1]), code_a[-1]
    nb, lb = int(code_b[:-1]), code_b[-1]
    if na == nb:
        return True
    if la == lb:
        diff = abs(na - nb)
        if diff == 1 or diff == 11:  # 11 == the 1<->12 wraparound
            return True
    return False
