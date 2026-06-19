"""
Stem separation via Demucs htdemucs (drums / bass / other / vocals).

Public API
----------
get_or_separate(track_path, *, cache_dir, target_sr) -> dict[str, np.ndarray]
    Returns all four stems as float32 [T, 2] arrays at target_sr.
    Cached as .npz beside the track so each track is only separated once.

get_drums_mono(track_path, *, cache_dir, target_sr) -> np.ndarray [T]
    Convenience wrapper: mono drums stem for beat detection.
"""

import os
import hashlib
import numpy as np
import torch
from pydub import AudioSegment


DEMUCS_MODEL  = "htdemucs"
DEMUCS_SR     = 44100          # model's native sample rate
STEMS         = ("drums", "bass", "other", "vocals")


def _cache_path(track_path: str, cache_dir: str) -> str:
    key = hashlib.md5(os.path.abspath(track_path).encode()).hexdigest()[:12]
    name = os.path.splitext(os.path.basename(track_path))[0]
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{name}_{key}.npz")


def _resample(arr: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    """Linear-phase resampling via julius (ships with demucs)."""
    if from_sr == to_sr:
        return arr
    from julius import resample_frac
    import math
    g = math.gcd(from_sr, to_sr)
    # arr shape [T, 2] → need [C, T] for julius
    t = torch.tensor(arr.T, dtype=torch.float32)
    r = resample_frac(t, from_sr // g, to_sr // g)
    return r.numpy().T   # back to [T, 2]


def get_or_separate(track_path: str, *, cache_dir: str, target_sr: int = 48000) -> dict:
    """
    Separate track into 4 stems. Returns dict keyed by stem name,
    each value a float32 numpy array of shape [T, 2] at target_sr.
    """
    cache = _cache_path(track_path, cache_dir)

    if os.path.exists(cache):
        data = np.load(cache)
        stems_44 = {s: data[s] for s in STEMS}
    else:
        print(f"  [stems] separating {os.path.basename(track_path)}…", flush=True)
        stems_44 = _separate(track_path)
        np.savez_compressed(cache, **stems_44)
        print(f"  [stems] cached → {os.path.basename(cache)}")

    # Resample to target_sr (all stems, lazily)
    return {s: _resample(stems_44[s], DEMUCS_SR, target_sr) for s in STEMS}


def get_drums_mono(track_path: str, *, cache_dir: str, target_sr: int = 48000) -> np.ndarray:
    """Mono drums stem at target_sr, shape [T]."""
    stems = get_or_separate(track_path, cache_dir=cache_dir, target_sr=target_sr)
    return stems["drums"].mean(axis=1)


def _separate(track_path: str) -> dict:
    """Run htdemucs on a track, return stems as float32 [T, 2] at DEMUCS_SR."""
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    seg = AudioSegment.from_file(track_path).set_channels(2).set_frame_rate(DEMUCS_SR)
    samples = (np.array(seg.get_array_of_samples(), dtype=np.float32)
               .reshape(-1, 2) / 32768.0)
    wav = torch.tensor(samples.T, dtype=torch.float32).unsqueeze(0)  # [1, 2, T]

    model = get_model(DEMUCS_MODEL)
    model.eval()
    with torch.no_grad():
        out = apply_model(model, wav, device="cpu", progress=False)
    # out: [1, 4, 2, T]  →  dict stem → [T, 2]
    return {
        s: out[0, i].numpy().T.astype(np.float32)
        for i, s in enumerate(model.sources)
    }
