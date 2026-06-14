"""
Mix quality evaluator — research-backed metrics.

Metrics (from ICASSP 2022 / ISMIR 2024 literature + auraloss / mir_eval):
  energy    — smoothed RMS envelope, no craters during crossfade (weight 40%)
  beats     — IBI (inter-beat interval) CV across the snippet (weight 30%)
  spectral  — spectral flux at transition midpoint vs rest (weight 20%)
  clipping  — peak samples near ±1.0 (weight 10%)

Overall 0-100. Grades: ✓ GOOD ≥70, △ OK ≥50, ✗ BAD <50.

Usage:
    from mixer.evaluate import evaluate_snippet, evaluate_all_snippets
    report = evaluate_snippet("output/snippets/transition_01.mp3")

CLI:
    python -m mixer.evaluate output/snippets/          # score whole folder
    python -m mixer.evaluate output/snippets/t01.mp3  # score one file
"""
from __future__ import annotations
import glob
import os
import sys

import librosa
import numpy as np

SR = 44100
WEIGHTS = {"energy": 0.40, "beats": 0.30, "spectral": 0.20, "clipping": 0.10}


# ── Signal helpers ────────────────────────────────────────────────────────────

def _smoothed_rms_db(y: np.ndarray, sr: int, smooth_sec: float = 2.0):
    hop   = int(sr * 0.05)
    frame = int(sr * 0.10)
    rms   = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]
    k     = max(1, int(smooth_sec / 0.05))
    rms_s = np.convolve(rms, np.ones(k) / k, mode="same")
    db    = librosa.amplitude_to_db(rms_s + 1e-9, ref=np.max)
    times = librosa.frames_to_time(np.arange(len(db)), sr=sr, hop_length=hop)
    return times, db


# ── Individual scorers ────────────────────────────────────────────────────────

def score_energy(times: np.ndarray, db: np.ndarray, snippet_dur: float) -> dict:
    """
    Penalise energy craters during the crossfade zone (between the 8s pre/post guards).
    Good crossfade: smooth plateau, no sudden silence.
    crater = mean_db - min_db in the zone; 0 is flat/perfect, >12 is problematic.
    """
    cf_start = 8.0
    cf_end   = max(cf_start + 1.0, snippet_dur - 8.0)
    mask     = (times >= cf_start) & (times <= cf_end)
    cf_db    = db[mask]

    if len(cf_db) == 0:
        return {"score": 50, "detail": "no data in crossfade zone"}

    min_db  = float(cf_db.min())
    mean_db = float(cf_db.mean())
    crater  = mean_db - min_db          # always ≥ 0
    score   = max(0, 100 - int(crater * 4))
    return {
        "score": score,
        "min_db": round(min_db, 1),
        "mean_db": round(mean_db, 1),
        "crater_db": round(crater, 1),
    }


def score_beats(y: np.ndarray, sr: int) -> dict:
    """
    IBI (inter-beat interval) coefficient of variation across the full snippet.
    Tight beats = low CV. CV > 0.20 means the beat grid is unstable / drifting.
    """
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times     = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_times) < 4:
        return {"score": 50, "detail": "too few beats detected"}

    ibis  = np.diff(beat_times)
    cv    = float(np.std(ibis) / np.mean(ibis))
    score = max(0, int(100 - cv * 500))
    return {"score": score, "ibi_cv": round(cv, 3)}


def score_clipping(y: np.ndarray, threshold: float = 0.99) -> dict:
    n_clipped = int(np.sum(np.abs(y) >= threshold))
    pct       = n_clipped / max(len(y), 1) * 100
    score     = max(0, 100 - int(pct * 100))
    return {"score": score, "clipped_pct": round(pct, 3)}


def score_spectral(y: np.ndarray, sr: int, snippet_dur: float) -> dict:
    """
    Spectral flux at the crossfade midpoint vs the rest of the snippet.
    A jarring spectral/key jump shows up as elevated flux at the blend point.
    ratio ~1.0 = smooth; ratio > 2.0 = jarring transition.
    """
    hop  = int(sr * 0.05)
    S    = np.abs(librosa.stft(y, hop_length=hop))
    flux = np.sqrt(np.sum(np.diff(S, axis=1) ** 2, axis=0))
    times = librosa.frames_to_time(np.arange(len(flux)), sr=sr, hop_length=hop)

    mid     = snippet_dur / 2
    window  = 4.0
    mid_m   = (times >= mid - window) & (times <= mid + window)
    rest_m  = ~mid_m

    if not mid_m.any() or not rest_m.any():
        return {"score": 50, "detail": "snippet too short for spectral analysis"}

    ratio = float(flux[mid_m].mean()) / (float(flux[rest_m].mean()) + 1e-9)
    score = max(0, int(100 - (ratio - 1.0) * 50))
    return {"score": score, "flux_ratio": round(ratio, 2)}


# ── Main entry ────────────────────────────────────────────────────────────────

def evaluate_snippet(path: str) -> dict:
    y, sr = librosa.load(path, sr=SR, mono=True)
    dur   = librosa.get_duration(y=y, sr=sr)
    times, db = _smoothed_rms_db(y, sr)

    scores = {
        "energy":   score_energy(times, db, dur),
        "beats":    score_beats(y, sr),
        "spectral": score_spectral(y, sr, dur),
        "clipping": score_clipping(y),
    }
    overall = sum(scores[k]["score"] * w for k, w in WEIGHTS.items())
    grade   = "✓ GOOD" if overall >= 70 else ("△ OK" if overall >= 50 else "✗ BAD")

    return {
        "file":    os.path.basename(path),
        "dur_sec": round(dur, 1),
        "scores":  scores,
        "overall": round(overall, 1),
        "grade":   grade,
    }


def evaluate_all_snippets(folder: str) -> list[dict]:
    paths = sorted(glob.glob(os.path.join(folder, "transition_*.mp3")))
    return [evaluate_snippet(p) for p in paths]


def print_report(reports: list[dict]):
    print(f"\n{'File':<22} {'Energy':>7} {'Beats':>6} {'Clip':>5} {'Spectral':>9}  {'Overall':>8}  Grade  Notes")
    print("─" * 100)
    for r in reports:
        s = r["scores"]
        notes = []
        if s["energy"].get("crater_db", 0) > 10:
            notes.append(f"crater {s['energy']['crater_db']:.0f}dB")
        if s["beats"].get("ibi_cv", 0) > 0.15:
            notes.append(f"beat drift cv={s['beats']['ibi_cv']}")
        if s["clipping"].get("clipped_pct", 0) > 0.1:
            notes.append(f"clipping {s['clipping']['clipped_pct']}%")
        if s["spectral"].get("flux_ratio", 0) > 2.0:
            notes.append(f"spectral jump x{s['spectral']['flux_ratio']}")
        print(
            f"{r['file']:<22} "
            f"{s['energy']['score']:>7} "
            f"{s['beats']['score']:>6} "
            f"{s['clipping']['score']:>5} "
            f"{s['spectral']['score']:>9}  "
            f"{r['overall']:>8.1f}  "
            f"{r['grade']:<7} "
            f"{', '.join(notes)}"
        )
    avg = sum(r["overall"] for r in reports) / len(reports) if reports else 0
    print("─" * 100)
    print(f"  Average: {avg:.1f}/100  ({len(reports)} snippets)\n")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "output/snippets"
    if os.path.isdir(target):
        reports = evaluate_all_snippets(target)
    else:
        reports = [evaluate_snippet(target)]
    print_report(reports)
