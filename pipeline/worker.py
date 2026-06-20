"""
djKyoko build worker.

Runs the full pipeline for one mix:
  1. Set up volume symlinks
  2. Select brain (weekly rotation or DJKYOKO_BRAIN env var)
  3. Download any missing tracks
  4. Build the mix
  5. Quality gate
  6. Upload to Mixcloud
  7. Exit (Railway cron requirement)

Usage:
  python -m pipeline.worker                    # weekly rotation brain
  python -m pipeline.worker --brain taleous    # specific brain
  python -m pipeline.worker --dry-run          # build + gate, no upload
"""

import argparse
import importlib
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from pipeline.quality_gate import check as quality_check
from pipeline.style_selector import current_brain

# ── Paths ─────────────────────────────────────────────────────────────────────

APP_DIR    = Path(__file__).parent.parent.resolve()
DATA_DIR   = Path(os.environ.get("DATA_DIR", "/data"))


def _setup_volume():
    """Symlink /app/downloads and /app/output into the persistent volume."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "downloads" / "new_tracks").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "downloads" / "library").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "output").mkdir(parents=True, exist_ok=True)

    dl_link = APP_DIR / "downloads"
    out_link = APP_DIR / "output"

    if not dl_link.exists():
        dl_link.symlink_to(DATA_DIR / "downloads")
        print(f"  linked {dl_link} → {DATA_DIR / 'downloads'}")

    if not out_link.exists():
        out_link.symlink_to(DATA_DIR / "output")
        print(f"  linked {out_link} → {DATA_DIR / 'output'}")


def _setup_mixcloud_token():
    """Write MIXCLOUD_TOKEN env var to ~/.mixcloud_token if present."""
    token = os.environ.get("MIXCLOUD_TOKEN")
    if token:
        token_path = Path.home() / ".mixcloud_token"
        token_path.write_text(token.strip())
        token_path.chmod(0o600)
        print("  Mixcloud token written from env var")


def _download_missing_tracks(brain_module):
    """Download any tracks from the brain that aren't on disk yet."""
    missing = [
        t for t in brain_module.TRACKS
        if not Path(t["path"]).exists()
    ]
    if not missing:
        print(f"  All {len(brain_module.TRACKS)} tracks present")
        return

    print(f"  Downloading {len(missing)} missing tracks...")
    for t in missing:
        path = Path(t["path"])
        video_id = path.stem
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"    yt-dlp {video_id} → {path.name}")
        result = subprocess.run([
            "yt-dlp",
            f"https://www.youtube.com/watch?v={video_id}",
            "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "--match-filter", "duration > 300",
            "-o", str(path.with_suffix("")) + ".%(ext)s",
            "--no-playlist",
        ], capture_output=True, text=True)
        if result.returncode != 0 or not path.exists():
            print(f"    FAIL: {video_id}\n{result.stderr[-500:]}")
            raise RuntimeError(f"Failed to download {video_id} ({t['label']})")
        print(f"    ✓ {path.name} ({path.stat().st_size / 1e6:.1f} MB)")


def _build(brain_name: str) -> Path:
    """Run build_set.py and return the output directory."""
    print(f"\n  Building: {brain_name}")
    result = subprocess.run(
        [sys.executable, str(APP_DIR / "build_set.py"), brain_name],
        cwd=str(APP_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(f"build_set.py exited {result.returncode}")

    # Find output dir from brain
    brain = importlib.import_module(f"brains.{brain_name}")
    return APP_DIR / "output" / brain.SET_NAME


def _generate_cover_art(set_dir: Path, brain_module) -> Path | None:
    """Fetch cover art from Pollinations FLUX. Returns path or None on failure."""
    art_dir = APP_DIR / "output" / "artwork"
    art_dir.mkdir(parents=True, exist_ok=True)
    out = art_dir / f"{set_dir.name}_cover.jpg"
    if out.exists():
        return out

    # Build a prompt from the first line of SET_NOTES
    first_line = getattr(brain_module, "SET_NOTES", "").split("\n")[0].strip()
    prompt = (
        f"cinematic dark electronic music album art, {first_line}, "
        "deep space, minimal, moody, high contrast, no text, photorealistic"
    )
    import urllib.parse
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1280&height=720&nologo=true"
    try:
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            out.write_bytes(r.content)
            print(f"  Cover art generated: {out.name}")
            return out
    except Exception as e:
        print(f"  Cover art failed: {e}")
    return None


def _stream_to_twitch(mp3_path: Path, cover_art: Path | None):
    """Stream mix + cover art to Twitch via FFmpeg. Blocks until stream ends."""
    key = os.environ.get("TWITCH_STREAM_KEY")
    if not key:
        print("  Twitch: TWITCH_STREAM_KEY not set, skipping")
        return

    rtmp_url = f"rtmp://live.twitch.tv/app/{key}"

    if cover_art and cover_art.exists():
        video_input = ["-loop", "1", "-i", str(cover_art)]
        video_codec = ["-vf", "scale=1280:720", "-c:v", "libx264",
                       "-preset", "veryfast", "-b:v", "2500k",
                       "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60"]
    else:
        # Black screen fallback
        video_input = ["-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30"]
        video_codec = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", "1000k", "-g", "60"]

    cmd = [
        "ffmpeg", "-re",
        *video_input,
        "-i", str(mp3_path),
        *video_codec,
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-shortest",          # stop when audio ends
        "-f", "flv", rtmp_url,
    ]

    print(f"  Streaming to Twitch...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("  Twitch stream ended cleanly ✓")
    else:
        print(f"  Twitch stream error: {result.stderr[-300:]}")


def _notify_sms(message: str):
    """Send SMS via Twilio. Silently skips if env vars not set."""
    sid   = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    frm   = os.environ.get("TWILIO_FROM")
    to    = os.environ.get("TWILIO_TO")
    if not all([sid, token, frm, to]):
        print("  SMS: env vars not set, skipping")
        return
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": frm, "To": to, "Body": message},
        timeout=15,
    )
    if r.status_code == 201:
        print(f"  SMS sent ✓")
    else:
        print(f"  SMS failed: {r.status_code} {r.text[:100]}")


def _upload(brain_name: str):
    """Run mixcloud_upload.py."""
    print(f"\n  Uploading: {brain_name}")
    result = subprocess.run(
        [sys.executable, str(APP_DIR / "scripts" / "mixcloud_upload.py"), brain_name],
        cwd=str(APP_DIR),
    )
    if result.returncode != 0:
        raise RuntimeError(f"mixcloud_upload.py exited {result.returncode}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brain",   help="Brain name override (else weekly rotation)")
    parser.add_argument("--dry-run", action="store_true", help="Build + gate but don't upload")
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  djKyoko Pipeline")
    print("═" * 60)

    # Setup
    _setup_volume()
    _setup_mixcloud_token()

    brain_name = args.brain or current_brain()
    print(f"\n  Brain: {brain_name}")

    # Load brain module
    sys.path.insert(0, str(APP_DIR))
    brain = importlib.import_module(f"brains.{brain_name}")

    # Download missing tracks
    _download_missing_tracks(brain)

    # Build
    t0 = time.time()
    set_dir = _build(brain_name)
    build_mins = (time.time() - t0) / 60
    print(f"\n  Build complete in {build_mins:.1f} min")

    # Quality gate
    print("\n  Running quality gate...")
    passed, report = quality_check(set_dir)
    print(report)

    if not passed:
        print("\n  ✗ Quality gate FAILED — aborting upload")
        sys.exit(2)

    if args.dry_run:
        print("\n  --dry-run: skipping upload")
        sys.exit(0)

    # Upload
    _upload(brain_name)

    # Cover art (generate if missing)
    cover_art = _generate_cover_art(set_dir, brain)

    # Stream to Twitch (blocks for duration of mix)
    mp3_path = set_dir / "FULL_SET.mp3"
    _stream_to_twitch(mp3_path, cover_art)

    # Notify
    set_url = f"https://www.mixcloud.com/louis-lapat/{brain.SET_NAME.replace('_', '-')}/"
    _notify_sms(f"djKyoko — new mix is live 🎧\n{brain.SET_NAME.replace('_', ' ').title()}\n{set_url}")

    print("\n" + "═" * 60)
    print("  djKyoko Pipeline COMPLETE")
    print("═" * 60 + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
