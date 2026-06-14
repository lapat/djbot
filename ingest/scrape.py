"""
Scrape a DJ's YouTube channel/search for long mixes.
Downloads metadata (title, description, comments) without audio first,
then optionally downloads audio for selected mixes.
"""
import json
import os
import subprocess
import tempfile
from typing import Optional


def search_mixes(artist_name: str, min_duration_sec: int = 2400, max_results: int = 30) -> list[dict]:
    """
    Search YouTube for long DJ mixes by artist name.
    Returns list of {youtube_id, title, duration_sec, url}.
    """
    query = f"{artist_name} DJ mix"
    print(f"Searching YouTube: '{query}' (min {min_duration_sec//60} min)...")

    result = subprocess.run([
        "yt-dlp",
        f"ytsearch{max_results}:{query}",
        "--print", "%(id)s\t%(title)s\t%(duration)s",
        "--no-download",
        "--match-filter", f"duration >= {min_duration_sec}",
        "--no-warnings",
    ], capture_output=True, text=True)

    mixes = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid_id, title, duration = parts[0], parts[1], parts[2]
        try:
            dur = int(duration)
        except ValueError:
            continue
        mixes.append({
            "youtube_id": vid_id,
            "title": title,
            "duration_sec": dur,
            "url": f"https://www.youtube.com/watch?v={vid_id}",
        })

    print(f"  Found {len(mixes)} mixes")
    return mixes


def fetch_metadata(youtube_id: str) -> dict:
    """
    Fetch description + top comments for a video without downloading audio.
    Returns {description, comments: [str, ...]}.
    """
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    # Get description via --print (fast, no temp files needed)
    desc_result = subprocess.run(
        ["yt-dlp", "--skip-download", "--print", "%(description)s", "--no-warnings", url],
        capture_output=True, text=True,
    )
    description = desc_result.stdout.strip() if desc_result.returncode == 0 else ""

    # Get comments via info.json (comments aren't available via --print)
    comments = []
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "%(id)s.%(ext)s")
        subprocess.run([
            "yt-dlp",
            "--skip-download",
            "--write-info-json",
            "--write-comments",
            "--max-comments", "30,all,0,0",
            "--output", out,
            "--no-warnings",
            url,
        ], capture_output=True, text=True)

        info_path = os.path.join(tmpdir, f"{youtube_id}.info.json")
        if os.path.exists(info_path):
            with open(info_path) as f:
                info = json.load(f)
            raw_comments = info.get("comments", []) or []
            comments = [c.get("text", "") for c in raw_comments if c.get("text")]

    return {"description": description, "comments": comments}


def download_audio(youtube_id: str, output_dir: str = "downloads/mixes") -> Optional[str]:
    """
    Download full mix audio as MP3. Returns local file path.
    These are big files (1hr+) — only call for mixes we want to analyze deeply.
    """
    os.makedirs(output_dir, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    out_template = os.path.join(output_dir, f"{youtube_id}.%(ext)s")

    result = subprocess.run([
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", out_template,
        "--no-playlist",
        "--print", "after_move:filepath",
        "--no-warnings",
        url,
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  [error] Download failed for {youtube_id}: {result.stderr[:200]}")
        return None

    path = result.stdout.strip().splitlines()[-1]
    if os.path.isfile(path):
        return path

    # Fallback
    mp3 = os.path.join(output_dir, f"{youtube_id}.mp3")
    return mp3 if os.path.isfile(mp3) else None
