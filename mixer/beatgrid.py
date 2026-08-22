"""
Beat grid analysis — run once per track, store forever.

A beat grid is just two numbers:
  bpm              — precise tempo (float, e.g. 122.984)
  beat_anchor_sample — sample number of the first detected kick

Every beat position is then deterministic:
  beat[n] = anchor + n * (sr * 60 / bpm)

No beat detection at mix time. Sync is pure arithmetic.
"""
from __future__ import annotations
import json
import os

import librosa
import librosa.feature.rhythm
import numpy as np
from scipy.signal import butter, sosfilt


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    """Load audio as mono float32, native sample rate."""
    y, sr = librosa.load(path, sr=None, mono=True)
    return y.astype(np.float32), int(sr)


def _bpm_from_beats(beats: np.ndarray) -> float:
    """Convert beat timestamps (seconds) to BPM via mean IBI."""
    if len(beats) < 2:
        return 0.0
    ibi = np.diff(beats)
    return float(60.0 / np.mean(ibi))


def _beat_this_bpm(path: str, start_sec: float = 0.0, duration: float = 30.0) -> float:
    """
    Use beat_this (SOTA detector) to measure actual BPM from audio file.
    More accurate than librosa autocorrelation — sub-0.1 BPM resolution.
    """
    import tempfile, soundfile as sf
    y, sr = librosa.load(path, sr=None, mono=True, offset=start_sec, duration=duration)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp = f.name
    sf.write(tmp, y, sr)
    try:
        from beat_this.inference import File2Beats
        beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(tmp)
        return _bpm_from_beats(beats)
    except Exception:
        return 0.0
    finally:
        os.unlink(tmp)


def _precise_bpm(y: np.ndarray, sr: int, hint_bpm: float) -> float:
    """
    Precise BPM via onset-strength autocorrelation.
    Constrained to ±10 BPM of the hint so we don't double/halve.
    """
    hop = 512
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    # librosa.feature.rhythm.tempo returns the peak of the tempogram (moved
    # here from librosa.beat.tempo in 0.10.0; the old alias is removed in 1.0)
    tempo = librosa.feature.rhythm.tempo(
        onset_envelope=env,
        sr=sr,
        hop_length=hop,
        start_bpm=hint_bpm,
        ac_size=8.0,    # 8-second autocorrelation window → high resolution
    )
    detected = float(np.atleast_1d(tempo)[0])
    # Snap to the power-of-2 octave closest to hint_bpm.
    # Fixes halving/doubling artifacts without a hard BPM range.
    candidate = detected
    while abs(candidate * 2 - hint_bpm) < abs(candidate - hint_bpm):
        candidate *= 2.0
    while abs(candidate / 2 - hint_bpm) < abs(candidate - hint_bpm):
        candidate /= 2.0
    detected = candidate
    # Final sanity: if still > 10 BPM off, the hint is probably more reliable
    if abs(detected - hint_bpm) > 10:
        return hint_bpm
    return detected


def _find_first_kick_sample(y: np.ndarray, sr: int, bpm: float) -> int:
    """
    Find the sample index of the first kick drum hit.

    Steps:
      1. Low-pass to ~200 Hz to isolate kick drum
      2. onset_detect with hop_length=32 (~0.7ms at 48kHz) + backtrack
      3. Reject onsets before 100ms (typical silence/noise floor)
      4. Return the first onset as an integer sample index
    """
    hop = 32   # ~0.7ms at 48kHz — very fine resolution
    min_sample = int(sr * 0.10)  # ignore first 100ms (noise floor)
    search_end  = int(sr * 8.0)  # only search first 8 seconds

    y_search = y[:search_end]

    # Low-pass filter for kick drum emphasis
    cutoff = min(200.0, sr * 0.45)
    sos = butter(4, cutoff / (sr / 2.0), btype='low', output='sos')
    y_lp = sosfilt(sos, y_search)

    onsets = librosa.onset.onset_detect(
        y=y_lp, sr=sr, hop_length=hop,
        backtrack=True, units='samples',
        delta=0.07,   # conservative threshold — only strong onsets
        wait=int(sr * 0.20 / hop),  # at least 200ms between onsets
    )

    # First onset after the noise floor
    valid = onsets[onsets >= min_sample]
    if len(valid) > 0:
        return int(valid[0])

    # Fallback: full-band onset
    onsets_fb = librosa.onset.onset_detect(
        y=y_search, sr=sr, hop_length=hop,
        backtrack=True, units='samples',
    )
    valid_fb = onsets_fb[onsets_fb >= min_sample]
    return int(valid_fb[0]) if len(valid_fb) > 0 else min_sample


def analyze_track(path: str, hint_bpm: float | None = None) -> dict:
    """
    Full beat grid analysis for a single track.

    BPM strategy (most accurate wins):
      1. beat_this on first 60s (SOTA, sub-0.1 BPM, used when available)
      2. librosa autocorrelation fallback (±1 BPM resolution)

    Returns dict with keys: bpm, beat_anchor_sample, sr, beat_period_samples.
    """
    y, sr = _load_mono(path)
    bpm_hint = hint_bpm or 120.0

    # Primary: beat_this — most accurate for house music tempos
    bpm = _beat_this_bpm(path, start_sec=0.0, duration=60.0)

    # Octave-snap toward hint, then validate
    if bpm > 0:
        candidate = bpm
        while abs(candidate * 2 - bpm_hint) < abs(candidate - bpm_hint):
            candidate *= 2.0
        while abs(candidate / 2 - bpm_hint) < abs(candidate - bpm_hint):
            candidate /= 2.0
        bpm = candidate

    # Fallback to librosa if beat_this failed or is wildly off
    if bpm <= 0 or abs(bpm - bpm_hint) > 15:
        bpm = _precise_bpm(y, sr, bpm_hint)

    # low_confidence: true when NEITHER detector could get close enough to be
    # trusted, so _precise_bpm's own last-resort fallback returned bpm_hint
    # verbatim — an unvalidated LLM guess standing in for a real measurement.
    # Detectable because a genuine measurement essentially never lands on the
    # hint to 2 decimal places by coincidence (confirmed live 2026-08-18: two
    # separate real tracks, "BPM=122.0000" and "BPM=130.0000" — exactly the
    # curator's hint, zero fractional noise — both caused real playback
    # problems downstream: one hung the whole job, the other passed the
    # narrow single-point phase gate but still sounded wrong end-to-end).
    low_confidence = abs(bpm - bpm_hint) < 0.01

    beat_period_samples = sr * 60.0 / bpm

    # Beat anchor
    anchor = _find_first_kick_sample(y, sr, bpm)

    return {
        "bpm":                 round(bpm, 4),
        "beat_anchor_sample":  anchor,
        "sr":                  sr,
        "beat_period_samples": beat_period_samples,
        "low_confidence":      low_confidence,
    }


# ── Cache helpers (stored alongside track_cache.json) ────────────────────────

_GRID_CACHE_FILE = "downloads/library/beatgrid_cache.json"


def load_grid_cache() -> dict:
    if os.path.exists(_GRID_CACHE_FILE):
        with open(_GRID_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_grid_cache(cache: dict):
    os.makedirs(os.path.dirname(_GRID_CACHE_FILE), exist_ok=True)
    with open(_GRID_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_or_analyze(path: str, hint_bpm: float | None = None, force: bool = False) -> dict:
    """
    Return cached beat grid for `path`, or analyze and cache it.
    Key = absolute path so the cache survives working-directory changes.
    """
    key = os.path.abspath(path)
    cache = load_grid_cache()

    # A cache entry missing "low_confidence" predates that safety flag being
    # added — it was never checked for the unvalidated-hint-fallback failure
    # mode (see analyze_track below), so trusting it as-is would silently
    # bypass the exact protection that flag exists for. Re-analyze rather
    # than guess at backfilling the flag from stale data (confirmed live:
    # this exact gap let a bad Snap!->2 Unlimited transition through, since
    # "2 Unlimited - No Limit"'s cache entry was written before this flag
    # existed).
    if not force and key in cache and "low_confidence" in cache[key]:
        return cache[key]

    print(f"  Analyzing beat grid: {os.path.basename(path)}")
    grid = analyze_track(path, hint_bpm=hint_bpm)
    conf_note = "  [LOW CONFIDENCE — unvalidated hint]" if grid.get("low_confidence") else ""
    print(f"    BPM={grid['bpm']:.4f}  anchor={grid['beat_anchor_sample']} samples  sr={grid['sr']}{conf_note}")

    cache[key] = grid
    save_grid_cache(cache)
    return grid


def snap_to_beat(target_sample: float, anchor: float, period: float) -> float:
    """Snap target_sample to the nearest beat in the grid. Returns float sample."""
    n = round((target_sample - anchor) / period)
    return anchor + n * period
