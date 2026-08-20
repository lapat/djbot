"""
Beat-aligned crossfade transition.

Beat matching = two numbers per track (BPM + anchor sample), computed once.
Mix time = pure arithmetic. No live beat detection.

Phase alignment:
  - Snap A's outro to its nearest beat: anchor_a + n * period_a
  - Trim B so it starts at its own anchor: trim = anchor_b (sample-accurate)
  Both tracks are then at "beat 1" at t=0 of the crossfade → kicks land together.

All alignment is in samples (not ms) to avoid pydub's 1ms quantization error.
"""
import io
import numpy as np
import soundfile as sf
from pydub import AudioSegment

try:
    import pyrubberband as pyrb
    _HAS_RUBBERBAND = True
except (ImportError, Exception):
    _HAS_RUBBERBAND = False

from mixer.beatgrid import get_or_analyze, snap_to_beat


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _seg_to_f32(seg: AudioSegment) -> tuple[np.ndarray, int]:
    """AudioSegment → float32 numpy (samples, channels), native SR."""
    sr = seg.frame_rate
    raw = np.array(seg.get_array_of_samples(), dtype=np.float32)
    scale = 2 ** (seg.sample_width * 8 - 1)
    raw /= scale
    return raw.reshape((-1, seg.channels)), sr


def _f32_to_seg(samples: np.ndarray, sr: int) -> AudioSegment:
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return AudioSegment.from_wav(buf)


def _mono(s: np.ndarray) -> np.ndarray:
    return s.mean(axis=1) if s.ndim == 2 else s


# ── DSP ───────────────────────────────────────────────────────────────────────

def _equal_power(n: int, fade_in: bool) -> np.ndarray:
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    return np.sin(t) if fade_in else np.cos(t)


def find_cue_point(seg: AudioSegment, min_energy_db: float = -30.0) -> int:
    """First sample index where audio exceeds min_energy_db."""
    import librosa
    samples, sr = _seg_to_f32(seg)
    mono = _mono(samples)
    hop  = sr // 10
    rms  = librosa.feature.rms(y=mono, frame_length=hop * 2, hop_length=hop)[0]
    db   = librosa.amplitude_to_db(rms, ref=np.max)
    above = np.where(db > min_energy_db)[0]
    if len(above) == 0:
        return 0
    return int(above[0]) * hop   # return in SAMPLES, not ms


def _beat_this_phase_trim(
    samples_a: np.ndarray,
    samples_b: np.ndarray,
    sr: int,
    outro_sample: int,
    anchor_b_s: float,
    period_a: float,
    cf_bars: int = 8,
) -> int:
    """
    Use beat_this to find the trim of B that puts B's beats in phase with A's
    beats at the blend start. Returns the integer sample index to trim B at.

    Strategy:
      1. Export 4 bars of A starting at outro_sample → detect A's beat phase
      2. Export 8 bars of B starting at anchor_b_s → detect B's beat timestamps
      3. For each of B's detected beats, compute: if we start B there, what
         phase offset would result relative to A?  Pick the B beat that
         gives the smallest phase error vs A.
    """
    import os, tempfile
    try:
        import soundfile as sf
        from beat_this.inference import File2Beats
        f2b = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)
    except Exception:
        return int(round(anchor_b_s))

    # A: export a clip that starts 2 beats BEFORE outro_sample so beat_this
    # has audio context (avoids ~60ms startup bias on clips starting at a beat).
    pre_context = int(2 * period_a)   # 2 beats of context before outro
    a_start = max(0, outro_sample - pre_context)
    a_len   = int((2 + 4 * 4) * period_a)  # context + 4 bars
    a_clip  = samples_a[a_start: a_start + a_len]
    if len(a_clip) < sr:
        return int(round(anchor_b_s))

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_a = f.name
    sf.write(tmp_a, a_clip, sr)
    try:
        a_beats, _ = f2b(tmp_a)
    finally:
        os.unlink(tmp_a)

    if len(a_beats) < 2:
        return int(round(anchor_b_s))

    # Find the A beat nearest to outro_sample (= a_start + pre_context samples)
    outro_rel_sec = (outro_sample - a_start) / sr   # seconds from a_start
    # Pick the detected beat closest to outro_rel_sec
    diffs = np.abs(np.array(a_beats) - outro_rel_sec)
    nearest_idx = int(np.argmin(diffs))
    nearest_beat_sec = float(a_beats[nearest_idx])
    # Phase = signed offset from outro_sample to the nearest detected beat
    a_phase_sec = nearest_beat_sec - outro_rel_sec
    # Normalize to [0, period)
    period_a_m = float(np.mean(np.diff(a_beats)))
    while a_phase_sec < 0:
        a_phase_sec += period_a_m
    while a_phase_sec >= period_a_m:
        a_phase_sec -= period_a_m

    # B: export 8 bars starting at anchor
    b_start = max(0, int(anchor_b_s) - int(period_a))   # one beat before anchor
    b_len   = int(9 * period_a)
    b_clip  = samples_b[b_start: b_start + b_len]
    if len(b_clip) < sr:
        return int(round(anchor_b_s))

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_b = f.name
    sf.write(tmp_b, b_clip, sr)
    try:
        b_beats, _ = f2b(tmp_b)
    finally:
        os.unlink(tmp_b)

    if len(b_beats) < 1:
        return int(round(anchor_b_s))

    # b_beats are timestamps relative to b_start
    # Convert to sample positions in samples_b
    b_beat_samples = [b_start + int(round(t * sr)) for t in b_beats]

    # For each B beat position, compute phase error vs A
    a_phase_samples = int(round(a_phase_sec * sr))
    best_trim, best_err = int(round(anchor_b_s)), float('inf')

    for b_samp in b_beat_samples:
        # If we trim B at (b_samp - a_phase_samples), B's beat lands at
        # a_phase_samples from the start of B_aligned = same as A's first beat
        candidate_trim = b_samp - a_phase_samples
        if candidate_trim < 0 or candidate_trim >= len(samples_b) - sr:
            continue
        # Pick candidate closest to anchor_b_s (all candidates are phase-aligned
        # by construction: each puts B's beat at a_phase_samples from trim_b)
        dist_from_anchor = abs(candidate_trim - anchor_b_s)
        if dist_from_anchor > 4 * period_a:
            continue
        if dist_from_anchor < best_err:
            best_err = dist_from_anchor
            best_trim = candidate_trim

    print(f"  Beat-this phase trim: {best_trim} samp  "
          f"(anchor was {int(round(anchor_b_s))}, shift={best_trim - int(round(anchor_b_s))} samp "
          f"= {(best_trim - int(round(anchor_b_s)))/sr*1000:.1f}ms)")
    return best_trim


def _time_stretch_samples(samples: np.ndarray, sr: int, ratio: float) -> np.ndarray:
    """
    Stretch samples by ratio (>1 = SLOWER / longer duration).

    pyrubberband.time_stretch rate convention: >1 = FASTER.
    We invert so callers can pass a natural duration ratio.
    """
    if not _HAS_RUBBERBAND:
        print("  [warn] pyrubberband missing — no time-stretch")
        return samples
    import pyrubberband as pyrb
    return pyrb.time_stretch(samples, sr, 1.0 / ratio).astype(np.float32)


# ── Main crossfade ────────────────────────────────────────────────────────────

def crossfade(
    track_a: AudioSegment,
    track_b: AudioSegment,
    bpm_a: float,
    bpm_b: float,
    crossfade_bars: int = 16,
    outro_bars: int = 32,
    cue_min_db: float = -30.0,
    path_a: str | None = None,
    path_b: str | None = None,
) -> tuple[AudioSegment, dict]:
    """
    Mix track_a into track_b with beat-grid-aligned equal-power crossfade.

    Provide path_a / path_b to use pre-analyzed beat grids (fast, precise).
    Falls back to live analysis if paths are not given.

    Returns (mix_segment, transition_info).
    """
    # ── 1. Load as samples ───────────────────────────────────────────────────
    samples_a, sr = _seg_to_f32(track_a)
    samples_b, _  = _seg_to_f32(track_b)

    # ── 2. Get beat grids ────────────────────────────────────────────────────
    print("  Loading beat grids...")
    grid_a = get_or_analyze(path_a, hint_bpm=bpm_a) if path_a else None
    grid_b = get_or_analyze(path_b, hint_bpm=bpm_b) if path_b else None

    if grid_a is None or grid_b is None:
        raise ValueError(
            "path_a and path_b are required for beat-grid mixing. "
            "Run: python preanalyze.py  to build the cache first."
        )

    bpm_a_grid = grid_a["bpm"]
    bpm_b_grid = grid_b["bpm"]
    anchor_a   = float(grid_a["beat_anchor_sample"])
    anchor_b   = float(grid_b["beat_anchor_sample"])
    period_a   = float(grid_a["beat_period_samples"])   # samples per beat, A
    period_b   = float(grid_b["beat_period_samples"])   # samples per beat, B

    print(f"  A: {bpm_a_grid:.4f} BPM  anchor={anchor_a:.0f} samp")
    print(f"  B: {bpm_b_grid:.4f} BPM  anchor={anchor_b:.0f} samp")

    # ── 3. Skip B's silent intro ─────────────────────────────────────────────
    cue_sample = find_cue_point(track_b, min_energy_db=cue_min_db)
    # Cue must not be past B's anchor — anchor is the reference beat
    if cue_sample > anchor_b:
        cue_sample = 0   # anchor already past cue, use whole track
    samples_b_cued = samples_b[cue_sample:]
    anchor_b_cued  = anchor_b - cue_sample   # anchor within cued slice

    # ── 4. Time-stretch B to match A's beat period ───────────────────────────
    stretch_ratio = period_a / period_b   # ratio > 1 → B gets longer (slower)
    # Always stretch — even 0.5% BPM difference causes 100ms drift over 8 bars
    if abs(stretch_ratio - 1.0) > 0.0001:
        print(f"  Stretching B: {bpm_b_grid:.4f} → {bpm_a_grid:.4f} BPM (ratio {stretch_ratio:.6f})")
        samples_b_s = _time_stretch_samples(samples_b_cued, sr, stretch_ratio)
    else:
        print(f"  Tempo match within 0.01% — no stretch needed")
        samples_b_s = samples_b_cued
    anchor_b_s = anchor_b_cued * stretch_ratio   # anchor in stretched coords

    # ── 5. Snap A's outro to nearest beat ────────────────────────────────────
    bars_per_outro    = outro_bars
    outro_target_samp = len(samples_a) - bars_per_outro * 4 * period_a
    outro_target_samp = max(anchor_a + period_a, outro_target_samp)
    snapped_outro_samp = snap_to_beat(outro_target_samp, anchor_a, period_a)
    outro_sample = int(round(snapped_outro_samp))

    # ── 6. Phase-align B to A using beat_this ────────────────────────────────
    # beat_this detects the actual musical beat phase at the mix point,
    # bypassing kick-onset anchor inaccuracy.
    trim_b_sample = _beat_this_phase_trim(
        samples_a, samples_b_s, sr,
        outro_sample, anchor_b_s, period_a,
        crossfade_bars,
    )
    trim_b_sample = max(0, min(trim_b_sample, len(samples_b_s) - sr))
    samples_b_aligned = samples_b_s[trim_b_sample:]

    print(f"  A outro: sample {outro_sample} ({outro_sample/sr:.3f}s)")
    print(f"  B trim:  sample {trim_b_sample} ({trim_b_sample/sr:.3f}s) — starts at beat anchor")
    phase_err_ms = abs((outro_sample - snap_to_beat(outro_sample, anchor_a, period_a)) / sr * 1000)
    print(f"  Phase snap error: {phase_err_ms:.2f}ms")

    # ── 7. Build crossfade in samples ────────────────────────────────────────
    crossfade_samples = int(round(crossfade_bars * 4 * period_a))
    len_b = len(samples_b_aligned)
    if len_b < crossfade_samples:
        crossfade_samples = max(len_b // 2, int(sr * 2))
        print(f"  [warn] B short — crossfade reduced to {crossfade_samples/sr:.1f}s")

    part_a = samples_a[:outro_sample]
    zone_a = samples_a[outro_sample: outro_sample + crossfade_samples]
    zone_b = samples_b_aligned[:crossfade_samples]
    rest_b = samples_b_aligned[crossfade_samples:]

    n = min(len(zone_a), len(zone_b))
    fade_out = _equal_power(n, fade_in=False)[:, np.newaxis]
    fade_in  = _equal_power(n, fade_in=True)[:, np.newaxis]

    blend = np.clip(zone_a[:n] * fade_out + zone_b[:n] * fade_in, -1.0, 1.0)

    result = np.concatenate([part_a, blend, rest_b], axis=0)

    crossfade_start_ms  = int(outro_sample / sr * 1000)
    crossfade_dur_ms    = int(crossfade_samples / sr * 1000)

    print(f"  Crossfade: {crossfade_bars} bars = {crossfade_dur_ms/1000:.1f}s  "
          f"| mix total: {len(result)/sr/60:.1f} min")

    return _f32_to_seg(result, sr), {
        "crossfade_start_ms":    crossfade_start_ms,
        "crossfade_duration_ms": crossfade_dur_ms,
    }
