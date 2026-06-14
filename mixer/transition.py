"""
Beat-aligned crossfade transition between two tracks.

Algorithm:
1. Time-stretch Track B to match Track A's BPM (pyrubberband)
2. Find crossfade start = N bars before Track A's end (snapped to downbeat)
3. Crossfade duration = M bars at Track A's BPM
4. Overlay: fade-out A + fade-in B over the crossfade window
5. Concatenate: [A pre-fade] + [crossfade zone] + [B post-fade-in]
"""
import io
import numpy as np
import librosa
import soundfile as sf
from pydub import AudioSegment

try:
    import pyrubberband as pyrb
    _HAS_RUBBERBAND = True
except (ImportError, Exception):
    _HAS_RUBBERBAND = False


def _load_stereo_pydub(path: str) -> AudioSegment:
    return AudioSegment.from_file(path).set_channels(2)


def _pydub_to_numpy(seg: AudioSegment) -> tuple[np.ndarray, int]:
    """Convert AudioSegment → float32 numpy array (n_samples, n_channels)."""
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
    n_channels = seg.channels
    samples = samples.reshape((-1, n_channels)) / (2 ** (seg.sample_width * 8 - 1))
    return samples, sr


def _numpy_to_pydub(samples: np.ndarray, sr: int) -> AudioSegment:
    """Convert float32 numpy (n_samples, n_channels) → AudioSegment."""
    n_channels = samples.shape[1] if samples.ndim == 2 else 1
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return AudioSegment.from_wav(buf)


def time_stretch(seg: AudioSegment, source_bpm: float, target_bpm: float) -> AudioSegment:
    """
    Time-stretch an AudioSegment from source_bpm to target_bpm.
    Falls back to no-op if pyrubberband / rubberband CLI is not available.
    """
    if abs(source_bpm - target_bpm) < 0.5:
        return seg  # close enough, skip stretch

    ratio = source_bpm / target_bpm  # <1 speeds up, >1 slows down

    if not _HAS_RUBBERBAND:
        print(f"  [warn] pyrubberband not available — skipping time-stretch ({source_bpm:.1f}→{target_bpm:.1f} BPM)")
        return seg

    print(f"  Time-stretching {source_bpm:.1f} → {target_bpm:.1f} BPM (ratio {ratio:.3f})")
    samples, sr = _pydub_to_numpy(seg)

    # pyrubberband expects (n_samples,) for mono or (n_samples, n_channels) for stereo
    stretched = pyrb.time_stretch(samples, sr, ratio)
    return _numpy_to_pydub(stretched, sr)


def crossfade(
    track_a: AudioSegment,
    track_b: AudioSegment,
    bpm_a: float,
    bpm_b: float,
    crossfade_bars: int = 32,
    outro_bars: int = 32,
) -> AudioSegment:
    """
    Produce a mixed AudioSegment: A fades into B.

    track_a         - full stereo AudioSegment for Track A
    track_b         - full stereo AudioSegment for Track B
    bpm_a / bpm_b   - detected BPMs
    crossfade_bars  - how many bars the fade takes
    outro_bars      - how many bars before Track A's end to begin the fade
    """
    seconds_per_bar_a = (60.0 / bpm_a) * 4  # 4 beats per bar
    crossfade_ms = int(seconds_per_bar_a * crossfade_bars * 1000)
    outro_start_ms = max(0, len(track_a) - int(seconds_per_bar_a * outro_bars * 1000))

    # Stretch B to match A's BPM
    track_b_stretched = time_stretch(track_b, bpm_b, bpm_a)

    # Trim track_b_stretched so it's long enough for the fade-in + remainder
    # We want: fade-in section from B (crossfade_ms) + rest of B
    if len(track_b_stretched) < crossfade_ms:
        print("  [warn] Track B is shorter than the crossfade window — reducing crossfade")
        crossfade_ms = len(track_b_stretched) // 2

    # Build the three segments
    part_a_clean = track_a[:outro_start_ms]

    fade_out_a = track_a[outro_start_ms: outro_start_ms + crossfade_ms].fade_out(crossfade_ms)
    fade_in_b  = track_b_stretched[:crossfade_ms].fade_in(crossfade_ms)
    blend_zone = fade_out_a.overlay(fade_in_b)

    rest_of_b = track_b_stretched[crossfade_ms:]

    mix = part_a_clean + blend_zone + rest_of_b

    print(f"  Crossfade: {crossfade_bars} bars = {crossfade_ms / 1000:.1f}s at {bpm_a:.1f} BPM")
    print(f"  Track A outro starts at: {outro_start_ms / 1000:.1f}s")
    print(f"  Final mix duration: {len(mix) / 1000 / 60:.1f} min")

    return mix
