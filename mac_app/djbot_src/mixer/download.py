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

    base_cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",       # best quality VBR
        "--output", output_template,
        "--no-playlist",
        "--remote-components", "ejs:github",
        "--print", "after_move:filepath",  # print final path
    ]
    # YouTube's anti-bot checks reliably 403 an anonymous session even with
    # the JS challenge solver enabled — a real logged-in browser session
    # (via --cookies-from-browser) is what actually gets through. Fall back
    # to no cookies if Chrome isn't installed/usable on this machine.
    result = subprocess.run(
        base_cmd + ["--cookies-from-browser", "chrome", url_or_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            base_cmd + [url_or_path], capture_output=True, text=True,
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
