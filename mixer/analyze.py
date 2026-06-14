"""BPM detection and beat timestamp extraction using librosa."""
import os
import librosa
import numpy as np


def analyze(path: str, sr: int = 44100) -> dict:
    """
    Load and analyze a track.

    Returns a dict with:
        path         - original file path
        bpm          - detected tempo (float)
        beat_times   - array of beat timestamps in seconds
        duration     - track duration in seconds
        sr           - sample rate used for analysis
    """
    print(f"  Analyzing: {os.path.basename(path)}")

    # Load mono at fixed SR for consistent analysis
    y, sr = librosa.load(path, sr=sr, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # BPM + beat frames
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Onset strength for energy envelope (used later for cue point heuristics)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    bpm = float(np.atleast_1d(tempo)[0])
    print(f"    BPM: {bpm:.1f}  |  Duration: {duration / 60:.1f} min  |  Beats: {len(beat_times)}")

    return {
        "path": path,
        "bpm": bpm,
        "beat_times": beat_times,
        "onset_env": onset_env,
        "duration": duration,
        "sr": sr,
    }


def find_outro_start(beat_times: np.ndarray, bars_from_end: int = 32) -> float:
    """
    Return the timestamp N bars from the end of the track.
    Used to find where to start fading out Track A.
    """
    beats_per_bar = 4
    n_beats = bars_from_end * beats_per_bar
    if len(beat_times) <= n_beats:
        return beat_times[len(beat_times) // 2]
    return float(beat_times[-n_beats])


def nearest_downbeat(beat_times: np.ndarray, target_time: float, beats_per_bar: int = 4) -> float:
    """
    Snap a target time to the nearest downbeat (every 4th beat).
    """
    # Downbeats are every 4 beats starting from beat 0
    downbeat_times = beat_times[::beats_per_bar]
    if len(downbeat_times) == 0:
        return target_time
    idx = int(np.argmin(np.abs(downbeat_times - target_time)))
    return float(downbeat_times[idx])
