"""Download audio from YouTube using yt-dlp."""
import os
import subprocess
import glob


def download(url_or_path: str, output_dir: str = "downloads") -> str:
    """
    Return path to a local MP3.
    If url_or_path is already a local file, return it as-is.
    Otherwise download from YouTube.
    """
    if os.path.isfile(url_or_path):
        return url_or_path

    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    result = subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",       # best quality VBR
            "--output", output_template,
            "--no-playlist",
            "--print", "after_move:filepath",  # print final path
            url_or_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr}")

    # yt-dlp --print filepath outputs the path on stdout
    output_path = result.stdout.strip().splitlines()[-1]
    if os.path.isfile(output_path):
        return output_path

    # Fallback: find the newest MP3 in the download dir
    mp3s = sorted(glob.glob(os.path.join(output_dir, "*.mp3")), key=os.path.getmtime)
    if mp3s:
        return mp3s[-1]

    raise FileNotFoundError(f"Could not locate downloaded file. yt-dlp stdout:\n{result.stdout}")
