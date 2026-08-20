"""
Audio feature tagger for DJ set building.

Extracts per-track metadata:
  - Musical key + scale → Camelot wheel notation
  - Energy (0-1, RMS-based)
  - Spectral brightness (warm vs bright)
  - Mood probability vectors (aggressive, relaxed, electronic, danceability)
    via Essentia TF models when available, else heuristic from spectral features
  - Dynamic range (compression level)

Results cached in downloads/library/tag_cache.json.
"""
import json
import os
import numpy as np

CACHE_PATH = "downloads/library/tag_cache.json"
MODELS_DIR = "downloads/models"

# Camelot wheel: (key, scale) → Camelot notation
# minor keys: 1A-12A, major keys: 1B-12B
_CAMELOT_MAP = {
    # Minor (A)
    ("A",  "minor"): "8A",  ("E",  "minor"): "9A",  ("B",  "minor"): "10A",
    ("F#", "minor"): "11A", ("Db", "minor"): "12A", ("Ab", "minor"): "1A",
    ("Eb", "minor"): "2A",  ("Bb", "minor"): "3A",  ("F",  "minor"): "4A",
    ("C",  "minor"): "5A",  ("G",  "minor"): "6A",  ("D",  "minor"): "7A",
    # Major (B)
    ("C",  "major"): "8B",  ("G",  "major"): "9B",  ("D",  "major"): "10B",
    ("A",  "major"): "11B", ("E",  "major"): "12B", ("B",  "major"): "1B",
    ("F#", "major"): "2B",  ("Db", "major"): "3B",  ("Ab", "major"): "4B",
    ("Eb", "major"): "5B",  ("Bb", "major"): "6B",  ("F",  "major"): "7B",
}


def _load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def _analyze_key(audio_44k):
    import essentia.standard as es
    key, scale, strength = es.KeyExtractor()(audio_44k)
    camelot = _CAMELOT_MAP.get((key, scale), "?")
    return {"key": key, "scale": scale, "camelot": camelot, "key_strength": round(float(strength), 3)}


def _analyze_energy_spectral(path):
    import librosa
    y, sr = librosa.load(path, sr=None, mono=True, duration=120)

    # RMS energy (normalized 0-1 relative to max possible)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    energy = float(np.mean(rms))
    energy_peak = float(np.max(rms))

    # Spectral centroid (brightness, Hz)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]
    brightness = float(np.mean(centroid))  # low ~1000Hz = warm, high ~3000Hz = bright

    # Dynamic range (difference between loud and quiet sections)
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    dynamic_range = float(np.percentile(rms_db, 95) - np.percentile(rms_db, 10))

    # Zero-crossing rate (percussiveness proxy)
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=y, hop_length=512)[0]))

    # Normalize energy 0-1 using 0.30 as "fully loud" house/techno ceiling
    # Jon Hopkins-style dynamic = ~0.05–0.08; hard compressed house = ~0.25
    energy_norm = min(1.0, energy / 0.30)

    return {
        "energy": round(energy_norm, 3),
        "energy_raw": round(energy, 6),
        "brightness_hz": round(brightness, 1),
        "dynamic_range_db": round(dynamic_range, 1),
        "zcr": round(zcr, 5),
    }


def _get_effnet_embeddings(audio_44k):
    """Extract Discogs-EffNet embeddings from audio. Returns None if backbone unavailable."""
    backbone_path = os.path.join(MODELS_DIR, "discogs-effnet-bs64-1.pb")
    if not os.path.exists(backbone_path):
        return None
    try:
        import essentia.standard as es
        extractor = es.TensorflowPredictEffnetDiscogs(
            graphFilename=backbone_path,
            output="PartitionedCall:1",
        )
        return extractor(audio_44k)   # shape (N, 1280)
    except Exception:
        return None


def _analyze_mood_tf(audio_44k):
    """
    Two-stage Essentia TF pipeline:
      1. backbone (discogs-effnet-bs64-1.pb) → embeddings (N, 1280)
      2. classification heads (mood_*-discogs-effnet-1.pb) → (N, 2) probabilities

    Returns None if models not available.
    """
    embeddings = _get_effnet_embeddings(audio_44k)
    if embeddings is None:
        return None

    try:
        import essentia.standard as es

        moods = {}
        head_map = {
            "mood_aggressive": "mood_aggressive-discogs-effnet-1.pb",
            "mood_happy":      "mood_happy-discogs-effnet-1.pb",
            "mood_relaxed":    "mood_relaxed-discogs-effnet-1.pb",
            "mood_sad":        "mood_sad-discogs-effnet-1.pb",
            "mood_electronic": "mood_electronic-discogs-effnet-1.pb",
            "danceability":    "danceability-discogs-effnet-1.pb",
        }

        for mood_name, head_file in head_map.items():
            head_path = os.path.join(MODELS_DIR, head_file)
            if not os.path.exists(head_path):
                continue
            try:
                predictor = es.TensorflowPredict2D(
                    graphFilename=head_path,
                    input="model/Placeholder",
                    output="model/Softmax",
                )
                activations = predictor(embeddings)   # shape (N, 2)
                moods[mood_name] = round(float(np.mean(activations[:, 1])), 3)
            except Exception:
                pass

        return moods if moods else None
    except Exception:
        return None


def _mood_heuristic(energy_data):
    """Approximate mood from spectral features when TF models unavailable."""
    e = energy_data["energy"]
    b = energy_data["brightness_hz"]
    dr = energy_data["dynamic_range_db"]

    # Very rough heuristics tuned for deep house / melodic techno
    mood_electronic = min(1.0, e * 1.5)            # energetic = electronic
    mood_aggressive = min(1.0, max(0, (e - 0.4) * 2.5))  # high energy = more aggressive
    mood_relaxed    = max(0.0, 1.0 - e * 1.5)      # inverse of energy
    mood_happy      = min(1.0, (b / 2500) * 0.8)   # brighter = happier
    mood_sad        = max(0.0, 1.0 - (b / 2500))   # darker = sadder
    danceability    = min(1.0, e * 0.8 + 0.2)      # house is always danceable

    return {
        "mood_electronic": round(mood_electronic, 3),
        "mood_aggressive": round(mood_aggressive, 3),
        "mood_relaxed":    round(mood_relaxed, 3),
        "mood_happy":      round(mood_happy, 3),
        "mood_sad":        round(mood_sad, 3),
        "danceability":    round(danceability, 3),
        "mood_source":     "heuristic",
    }


def analyze_track(path: str, force: bool = False) -> dict:
    """
    Analyze a track and return (and cache) its tags.
    Returns dict with: key, scale, camelot, energy, brightness_hz,
                       dynamic_range_db, mood_*, danceability.
    """
    abs_path = os.path.abspath(path)
    cache = _load_cache()

    if not force and abs_path in cache:
        return cache[abs_path]

    print(f"  Tagging: {os.path.basename(path)}")

    import essentia.standard as es

    # Load at 44100 Hz (standard for Essentia analysis)
    loader = es.MonoLoader(filename=abs_path, sampleRate=44100)
    audio = loader()

    tags = {}

    # Key
    try:
        tags.update(_analyze_key(audio))
    except Exception as e:
        print(f"    [warn] key detection failed: {e}")
        tags.update({"key": "?", "scale": "?", "camelot": "?", "key_strength": 0.0})

    # Energy + spectral
    try:
        tags.update(_analyze_energy_spectral(abs_path))
    except Exception as e:
        print(f"    [warn] energy analysis failed: {e}")

    # Mood (TF models first, heuristic fallback)
    mood = _analyze_mood_tf(audio)
    if mood:
        tags.update(mood)
        tags["mood_source"] = "essentia-tf"
    else:
        tags.update(_mood_heuristic(tags))

    print(f"    Key: {tags.get('key','?')} {tags.get('scale','?')} → {tags.get('camelot','?')}  "
          f"Energy: {tags.get('energy', 0):.2f}  "
          f"Electronic: {tags.get('mood_electronic', 0):.2f}  "
          f"Relaxed: {tags.get('mood_relaxed', 0):.2f}")

    cache[abs_path] = tags
    _save_cache(cache)
    return tags


def get_tags(path: str) -> dict:
    """Return cached tags, or analyze if not cached."""
    abs_path = os.path.abspath(path)
    cache = _load_cache()
    if abs_path in cache:
        return cache[abs_path]
    return analyze_track(path)


def camelot_compatible(key_a: str, key_b: str) -> tuple[bool, str]:
    """
    Check harmonic compatibility between two Camelot keys.
    Returns (compatible, relationship).

    Compatible pairs:
      - Same key (perfect match)
      - Same number, adjacent letter (A↔B: relative major/minor)
      - Adjacent number, same letter (±1 on wheel: energy shift)
    """
    if key_a == "?" or key_b == "?":
        return True, "unknown"
    if key_a == key_b:
        return True, "perfect match"

    # Parse: "8A" → (8, "A")
    try:
        num_a, letter_a = int(key_a[:-1]), key_a[-1]
        num_b, letter_b = int(key_b[:-1]), key_b[-1]
    except (ValueError, IndexError):
        return True, "parse error"

    if num_a == num_b and letter_a != letter_b:
        return True, "relative major/minor"

    diff = (num_b - num_a) % 12
    if diff in (1, 11) and letter_a == letter_b:
        return True, "energy shift ±1"

    return False, f"clash ({key_a}→{key_b})"
