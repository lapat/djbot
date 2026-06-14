"""
Beat-aligned crossfade transition between two tracks.

Algorithm:
1. Find Track B's first beat (cue point) — skip quiet intros
2. Time-stretch Track B to match Track A's BPM (pyrubberband)
3. Find crossfade start = N bars before Track A's end
4. Apply equal-power (constant-power) crossfade: A fades with cos, B with sin
5. Concatenate: [A pre-fade] + [crossfade zone] + [B after cue+fade]

Equal-power crossfade maintains perceived loudness throughout the transition.
Linear fades create a -3dB (or worse) energy valley at the midpoint.
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


def _pydub_to_numpy(seg: AudioSegment) -> tuple[np.ndarray, int]:
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
    n_channels = seg.channels
    samples = samples.reshape((-1, n_channels)) / (2 ** (seg.sample_width * 8 - 1))
    return samples, sr


def _numpy_to_pydub(samples: np.ndarray, sr: int) -> AudioSegment:
    n_channels = samples.shape[1] if samples.ndim == 2 else 1
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return AudioSegment.from_wav(buf)


def _apply_equal_power_fade(samples: np.ndarray, fade_in: bool) -> np.ndarray:
    """
    Apply an equal-power (cosine) fade curve.
    fade_in=True:  silence → full (cos from π/2 → 0, sin from 0 → 1)
    fade_in=False: full → silence
    Maintains constant perceived loudness when overlaid with the opposite curve.
    """
    n = len(samples)
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    curve = np.sin(t) if fade_in else np.cos(t)
    if samples.ndim == 2:
        curve = curve[:, np.newaxis]
    return samples * curve


def find_cue_point(seg: AudioSegment, min_energy_db: float = -30.0) -> int:
    """
    Find the first millisecond where audio energy crosses min_energy_db.
    Skips quiet intros (fade-ins, silence before the beat drops).
    Returns offset in milliseconds.
    """
    samples, sr = _pydub_to_numpy(seg)
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples

    # Compute RMS in 100ms windows
    hop_samples = sr // 10  # 100ms
    rms = librosa.feature.rms(y=mono, frame_length=hop_samples * 2, hop_length=hop_samples)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)

    # First window that exceeds the energy threshold
    above = np.where(rms_db > min_energy_db)[0]
    if len(above) == 0:
        return 0
    cue_frame = int(above[0])
    cue_ms = cue_frame * 100  # each frame = 100ms
    print(f"  Cue point detected at {cue_ms / 1000:.1f}s (first frame above {min_energy_db} dB)")
    return cue_ms


def time_stretch(seg: AudioSegment, source_bpm: float, target_bpm: float) -> AudioSegment:
    """Time-stretch an AudioSegment from source_bpm to target_bpm."""
    if abs(source_bpm - target_bpm) < 0.5:
        return seg

    ratio = source_bpm / target_bpm

    if not _HAS_RUBBERBAND:
        print(f"  [warn] pyrubberband not available — skipping time-stretch ({source_bpm:.1f}→{target_bpm:.1f} BPM)")
        return seg

    print(f"  Time-stretching {source_bpm:.1f} → {target_bpm:.1f} BPM (ratio {ratio:.3f})")
    samples, sr = _pydub_to_numpy(seg)
    stretched = pyrb.time_stretch(samples, sr, ratio)
    return _numpy_to_pydub(stretched, sr)


def crossfade(
    track_a: AudioSegment,
    track_b: AudioSegment,
    bpm_a: float,
    bpm_b: float,
    crossfade_bars: int = 32,
    outro_bars: int = 32,
    cue_min_db: float = -30.0,
) -> AudioSegment:
    """
    Produce a mixed AudioSegment: A fades into B with an equal-power crossfade.

    track_a / track_b  - full stereo AudioSegments
    bpm_a / bpm_b      - detected BPMs
    crossfade_bars     - length of the overlap in bars
    outro_bars         - how many bars from Track A's end to start fading
    cue_min_db         - energy threshold for Track B's cue point detection
    """
    # --- Cue point: skip quiet intro of Track B ---
    cue_ms = find_cue_point(track_b, min_energy_db=cue_min_db)
    track_b_cued = track_b[cue_ms:]

    # --- BPM match ---
    track_b_stretched = time_stretch(track_b_cued, bpm_b, bpm_a)

    # --- Timing ---
    seconds_per_bar = (60.0 / bpm_a) * 4
    crossfade_ms = int(seconds_per_bar * crossfade_bars * 1000)
    outro_start_ms = max(0, len(track_a) - int(seconds_per_bar * outro_bars * 1000))

    if len(track_b_stretched) < crossfade_ms:
        crossfade_ms = max(len(track_b_stretched) // 2, 1000)
        print(f"  [warn] Track B short — crossfade reduced to {crossfade_ms / 1000:.1f}s")

    # --- Slice audio regions ---
    part_a_clean = track_a[:outro_start_ms]
    zone_a = track_a[outro_start_ms: outro_start_ms + crossfade_ms]
    zone_b = track_b_stretched[:crossfade_ms]
    rest_b = track_b_stretched[crossfade_ms:]

    # --- Equal-power fade via numpy ---
    samples_a, sr = _pydub_to_numpy(zone_a)
    samples_b, _  = _pydub_to_numpy(zone_b)

    # Pad shorter array if sizes differ by a sample or two (rounding)
    n = min(len(samples_a), len(samples_b))
    samples_a, samples_b = samples_a[:n], samples_b[:n]

    faded_a = _apply_equal_power_fade(samples_a, fade_in=False)
    faded_b = _apply_equal_power_fade(samples_b, fade_in=True)
    blend_samples = np.clip(faded_a + faded_b, -1.0, 1.0)

    blend_zone = _numpy_to_pydub(blend_samples, sr)

    mix = part_a_clean + blend_zone + rest_b

    print(f"  Crossfade: {crossfade_bars} bars = {crossfade_ms / 1000:.1f}s at {bpm_a:.1f} BPM")
    print(f"  Track A outro starts at: {outro_start_ms / 1000:.1f}s")
    print(f"  Track B cued to: {cue_ms / 1000:.1f}s")
    print(f"  Final mix duration: {len(mix) / 1000 / 60:.1f} min")

    return mix
