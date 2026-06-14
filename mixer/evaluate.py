"""
Mix quality evaluator.

Scores a mix file across five dimensions, each 0-100:
  energy    — RMS continuity through the crossfade (no craters)
  beats     — beat phase alignment at the transition point
  silence   — absence of prolonged silence gaps
  clipping  — absence of digital clipping
  bpm_drift — tempo stability through the mix

Usage:
    from mixer.evaluate import evaluate
    report = evaluate("output/mix.mp3", transition_start_sec=200.0, crossfade_sec=30.0)
    print(report)

Or CLI:
    python -m mixer.evaluate output/mix.mp3 --transition 200 --crossfade 30
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict

import librosa
import numpy as np


# ── helpers ──────────────────────────────────────────────────────────────────

def _rms_db_curve(y: np.ndarray, sr: int, smooth_sec: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (times, rms_db) using a smoothed energy envelope.
    Uses 50ms hops for resolution, then applies a 1-second rolling mean.
    This avoids false 'craters' from normal silence between beats.
    """
    hop = int(sr * 0.05)       # 50ms hop
    frame = int(sr * 0.1)      # 100ms frame
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]

    # Smooth with rolling mean over smooth_sec seconds
    smooth_frames = max(1, int(smooth_sec / 0.05))
    kernel = np.ones(smooth_frames) / smooth_frames
    rms_smooth = np.convolve(rms, kernel, mode="same")

    rms_db = librosa.amplitude_to_db(rms_smooth + 1e-9, ref=1.0)
    times = librosa.frames_to_time(np.arange(len(rms_db)), sr=sr, hop_length=hop)
    return times, rms_db


def _beats_in_window(y: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray:
    """Return beat timestamps inside [start_sec, end_sec]."""
    start = int(start_sec * sr)
    end   = int(end_sec   * sr)
    clip  = y[start:end]
    if len(clip) < sr:
        return np.array([])
    _, beat_frames = librosa.beat.beat_track(y=clip, sr=sr)
    beats = librosa.frames_to_time(beat_frames, sr=sr) + start_sec
    return beats


# ── scores ───────────────────────────────────────────────────────────────────

def score_energy_continuity(
    times: np.ndarray,
    rms_db: np.ndarray,
    transition_start: float,
    crossfade_duration: float,
    crater_threshold_db: float = -35.0,
) -> dict:
    """
    Score 0-100: penalise energy craters inside the crossfade window.
    A crater is any 200ms window that drops below crater_threshold_db.
    """
    t_end = transition_start + crossfade_duration
    mask = (times >= transition_start) & (times <= t_end)
    zone_db = rms_db[mask]

    if len(zone_db) == 0:
        return {"score": 0, "detail": "no data in crossfade window"}

    n_craters = int(np.sum(zone_db < crater_threshold_db))
    min_db    = float(zone_db.min())
    mean_db   = float(zone_db.mean())
    # Score: 100 if zero craters, penalise 5 pts per crater frame
    score = max(0, 100 - n_craters * 5)
    return {
        "score": score,
        "min_db": round(min_db, 1),
        "mean_db": round(mean_db, 1),
        "crater_frames": n_craters,
        "threshold_db": crater_threshold_db,
    }


def score_silence(
    rms_db: np.ndarray,
    silence_threshold_db: float = -50.0,
    min_run_frames: int = 5,          # 5 × 200ms = 1 second of silence
) -> dict:
    """
    Score 0-100: penalise prolonged silence anywhere in the mix.
    Short transient gaps (kick gaps etc.) are normal; sustained silence is not.
    """
    silent = rms_db < silence_threshold_db
    # Count runs of consecutive silent frames
    runs = []
    run = 0
    for s in silent:
        if s:
            run += 1
        else:
            if run >= min_run_frames:
                runs.append(run)
            run = 0
    if run >= min_run_frames:
        runs.append(run)

    n_runs = len(runs)
    total_silent_sec = sum(runs) * 0.2  # each frame = 200ms
    score = max(0, 100 - n_runs * 20)
    return {
        "score": score,
        "silence_runs": n_runs,
        "total_silent_sec": round(total_silent_sec, 1),
    }


def score_clipping(y: np.ndarray, threshold: float = 0.99) -> dict:
    """
    Score 0-100: penalise digital clipping (samples near ±1.0).
    """
    n_clipped = int(np.sum(np.abs(y) >= threshold))
    pct = n_clipped / max(len(y), 1) * 100
    score = max(0, 100 - int(pct * 50))  # 2% clipping → score 0
    return {
        "score": score,
        "clipped_samples": n_clipped,
        "clipped_pct": round(pct, 3),
    }


def score_beat_alignment(
    y: np.ndarray,
    sr: int,
    transition_start: float,
    crossfade_duration: float,
    window_sec: float = 4.0,
) -> dict:
    """
    Score 0-100: how well Track A and Track B beats align at the transition.

    We look at two 4-second windows:
      - just before the transition (end of Track A)
      - just after transition_start + crossfade/2 (Track B playing)
    Then compute the mean inter-beat interval (IBI) in each and compare.
    Perfect match = 0ms difference = 100. 20ms difference ≈ 0.
    """
    a_end = transition_start
    a_start = max(0.0, a_end - window_sec)
    b_start = transition_start + crossfade_duration * 0.5
    b_end   = b_start + window_sec

    beats_a = _beats_in_window(y, sr, a_start, a_end)
    beats_b = _beats_in_window(y, sr, b_start, b_end)

    def mean_ibi(beats):
        if len(beats) < 2:
            return None
        return float(np.mean(np.diff(beats)))

    ibi_a = mean_ibi(beats_a)
    ibi_b = mean_ibi(beats_b)

    if ibi_a is None or ibi_b is None:
        return {"score": 50, "detail": "insufficient beats in window", "ibi_a_ms": None, "ibi_b_ms": None}

    bpm_a = _normalize_bpm(60.0 / ibi_a)
    bpm_b = _normalize_bpm(60.0 / ibi_b, reference=bpm_a)
    diff_bpm = abs(bpm_a - bpm_b)
    # 0 BPM diff → 100; 10 BPM diff → 0
    score = max(0, int(100 - diff_bpm * 10))
    return {
        "score": score,
        "bpm_diff": round(diff_bpm, 1),
        "bpm_before_transition": round(bpm_a, 1),
        "bpm_after_transition": round(bpm_b, 1),
    }


def _normalize_bpm(bpm: float, reference: float | None = None) -> float:
    """
    Fold a BPM into [80, 180] range by doubling/halving to correct octave errors.
    Librosa often returns half-time (e.g. 63 BPM instead of 126 BPM).
    If reference is given, snap to closest octave relative to it.
    """
    if reference:
        # snap to reference within a 2x factor
        for factor in [1.0, 2.0, 0.5]:
            if abs(bpm * factor - reference) < abs(bpm - reference):
                bpm = bpm * factor
        return bpm
    # Fold into [80, 180] without a reference
    while bpm < 80:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm


def score_bpm_drift(
    y: np.ndarray,
    sr: int,
    segment_sec: float = 30.0,
) -> dict:
    """
    Score 0-100: tempo stability across the full mix.
    Splits mix into 30s segments, measures BPM in each, penalises variance.
    Uses octave normalization to correct librosa half/double-time errors.
    """
    duration = librosa.get_duration(y=y, sr=sr)
    n_segments = max(1, int(duration // segment_sec))
    raw_bpms = []
    for i in range(n_segments):
        start = int(i * segment_sec * sr)
        end   = int(min((i + 1) * segment_sec * sr, len(y)))
        clip  = y[start:end]
        if len(clip) < sr * 4:
            continue
        tempo, _ = librosa.beat.beat_track(y=clip, sr=sr)
        raw_bpms.append(float(np.atleast_1d(tempo)[0]))

    if len(raw_bpms) < 2:
        return {"score": 100, "detail": "too short to measure drift"}

    # Normalize: first pass gets a reference BPM from the median
    ref = float(np.median([_normalize_bpm(b) for b in raw_bpms]))
    bpms = [_normalize_bpm(b, reference=ref) for b in raw_bpms]

    std = float(np.std(bpms))
    score = max(0, int(100 - std * 10))
    return {
        "score": score,
        "bpm_mean": round(float(np.mean(bpms)), 1),
        "bpm_std": round(std, 2),
        "bpm_segments": [round(b, 1) for b in bpms],
    }


# ── main entry ────────────────────────────────────────────────────────────────

def evaluate(
    mix_path: str,
    transition_start_sec: float,
    crossfade_sec: float,
    sr: int = 44100,
) -> dict:
    """
    Run all five scorers on a mix file. Returns a report dict.
    """
    print(f"Evaluating: {mix_path}")
    y, sr = librosa.load(mix_path, sr=sr, mono=True)
    times, rms_db = _rms_db_curve(y, sr)

    report = {
        "file": mix_path,
        "duration_sec": round(librosa.get_duration(y=y, sr=sr), 1),
        "transition_start_sec": transition_start_sec,
        "crossfade_sec": crossfade_sec,
        "scores": {},
    }

    print("  Scoring energy continuity...")
    report["scores"]["energy"]    = score_energy_continuity(times, rms_db, transition_start_sec, crossfade_sec)
    print("  Scoring silence...")
    report["scores"]["silence"]   = score_silence(rms_db)
    print("  Scoring clipping...")
    report["scores"]["clipping"]  = score_clipping(y)
    print("  Scoring beat alignment...")
    report["scores"]["beats"]     = score_beat_alignment(y, sr, transition_start_sec, crossfade_sec)
    print("  Scoring BPM drift...")
    report["scores"]["bpm_drift"] = score_bpm_drift(y, sr)

    # Overall = weighted mean
    weights = {"energy": 0.35, "beats": 0.30, "silence": 0.15, "clipping": 0.10, "bpm_drift": 0.10}
    overall = sum(report["scores"][k]["score"] * w for k, w in weights.items())
    report["overall"] = round(overall, 1)

    return report


def _print_report(report: dict):
    print(f"\n{'═'*50}")
    print(f"  MIX QUALITY REPORT")
    print(f"{'─'*50}")
    print(f"  File     : {report['file']}")
    print(f"  Duration : {report['duration_sec']}s ({report['duration_sec']/60:.1f} min)")
    print(f"  Crossfade: {report['transition_start_sec']}s → "
          f"{report['transition_start_sec'] + report['crossfade_sec']}s "
          f"({report['crossfade_sec']}s)")
    print(f"{'─'*50}")
    for key, data in report["scores"].items():
        sc = data["score"]
        bar = "█" * (sc // 5) + "░" * (20 - sc // 5)
        detail = {k: v for k, v in data.items() if k != "score"}
        print(f"  {key:<12} [{bar}] {sc:3d}/100")
        for k, v in detail.items():
            print(f"               {k}: {v}")
    print(f"{'─'*50}")
    print(f"  OVERALL  [{('█' * int(report['overall'] // 5)):<20}] {report['overall']:5.1f}/100")
    print(f"{'═'*50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a DJ mix file.")
    parser.add_argument("mix", help="Path to mix MP3/WAV")
    parser.add_argument("--transition", type=float, required=True,
                        help="Transition start time in seconds")
    parser.add_argument("--crossfade", type=float, required=True,
                        help="Crossfade duration in seconds")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    report = evaluate(args.mix, args.transition, args.crossfade)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
