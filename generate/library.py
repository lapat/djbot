"""
Track library: find tracks on YouTube, download, analyze BPM.
Caches results so we don't re-download.
"""
import json
import os
import subprocess
import sqlite3

import librosa
import numpy as np

LIBRARY_DIR  = "downloads/library"
CACHE_PATH   = "downloads/library/track_cache.json"


def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def find_on_youtube(artist: str, title: str, max_duration_sec: int = 900) -> str | None:
    """
    Search YouTube for a track and return its video ID.
    Filters out DJ sets / mixes by rejecting anything longer than max_duration_sec.
    """
    query = f"{artist} {title} official audio"
    result = subprocess.run(
        [
            "yt-dlp", f"ytsearch5:{query}",
            "--print", "%(id)s\t%(duration)s\t%(title)s",
            "--no-download", "--no-warnings",
            "--match-filter", f"duration <= {max_duration_sec}",
        ],
        capture_output=True, text=True,
    )
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        vid_id = parts[0].strip()
        if vid_id and len(vid_id) == 11:
            return vid_id
    return None


def download_track(youtube_id: str, title: str = "") -> str | None:
    """Download a track as MP3. Returns local path or None."""
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    out_path = os.path.join(LIBRARY_DIR, f"{youtube_id}.mp3")
    if os.path.exists(out_path):
        return out_path

    url = f"https://www.youtube.com/watch?v={youtube_id}"
    result = subprocess.run([
        "yt-dlp",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
        "--output", os.path.join(LIBRARY_DIR, "%(id)s.%(ext)s"),
        "--no-playlist", "--no-warnings",
        url,
    ], capture_output=True, text=True)

    return out_path if os.path.exists(out_path) else None


def analyze_track(path: str) -> dict:
    """Return BPM and duration for a local audio file."""
    y, sr = librosa.load(path, sr=44100, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    # Fold into house/deep-house range [100, 135]
    while bpm < 100: bpm *= 2
    while bpm > 135: bpm /= 2
    duration = librosa.get_duration(y=y, sr=sr)
    return {"bpm": round(bpm, 1), "duration_sec": round(duration, 1)}


def get_track(artist: str, title: str, cache: dict = None) -> dict | None:
    """
    Full pipeline: search → download → analyze.
    Returns {artist, title, youtube_id, path, bpm, duration_sec} or None.
    """
    if cache is None:
        cache = _load_cache()

    cache_key = f"{artist}||{title}"
    if cache_key in cache and os.path.exists(cache[cache_key].get("path", "")):
        return cache[cache_key]

    print(f"  Finding: {artist} - {title}")
    vid_id = find_on_youtube(artist, title)
    if not vid_id:
        print(f"    [not found on YouTube]")
        return None

    path = download_track(vid_id, title)
    if not path:
        print(f"    [download failed]")
        return None

    info = analyze_track(path)
    print(f"    → {vid_id}  BPM:{info['bpm']}  {info['duration_sec']/60:.1f}min")

    entry = {
        "artist": artist,
        "title": title,
        "youtube_id": vid_id,
        "path": path,
        **info,
    }
    cache[cache_key] = entry
    _save_cache(cache)
    return entry


def build_library(track_list: list[dict], max_tracks: int = 12) -> list[dict]:
    """
    Given a list of {artist, title} dicts, download and analyze up to max_tracks.
    Returns a list of fully-analyzed track dicts, sorted by BPM.
    """
    cache = _load_cache()
    library = []

    for t in track_list:
        if len(library) >= max_tracks:
            break
        entry = get_track(t["artist"], t["title"], cache)
        if entry:
            library.append(entry)

    # Sort by BPM so adjacent tracks blend easily
    library.sort(key=lambda t: t["bpm"])
    return library
