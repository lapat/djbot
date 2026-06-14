"""
Upload a DJ set to YouTube as an unlisted video.

One-time setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "YouTube Data API v3"
  3. APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
     Application type: Desktop app
  4. Download the JSON → save as client_secrets.json in this folder
  5. Run: python upload_youtube.py --auth
     (opens browser, you approve, token saved to .youtube_token.json)
  6. Run: python upload_youtube.py --set output/sorry_i_am_late/ [--cover path/to/img.jpg]

Usage:
  python upload_youtube.py --auth
  python upload_youtube.py --set output/hours_before_light/
  python upload_youtube.py --set output/sorry_i_am_late/ --cover art/solomun_cover.jpg
"""
import argparse, json, os, sys, subprocess, tempfile

SECRETS_FILE = "client_secrets.json"
TOKEN_FILE   = ".youtube_token.json"
SCOPES       = ["https://www.googleapis.com/auth/youtube.upload"]


# ── OAuth ─────────────────────────────────────────────────────────────────────

def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(SECRETS_FILE):
                print("\nMissing client_secrets.json. Setup steps:\n")
                print("  1. Go to https://console.cloud.google.com/")
                print("  2. Create project → Enable 'YouTube Data API v3'")
                print("  3. APIs & Services → Credentials → Create OAuth 2.0 Client ID")
                print("     Application type: Desktop app")
                print("  4. Download JSON → save as client_secrets.json here")
                print("  5. Run: python upload_youtube.py --auth\n")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=8765)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"  Token saved to {TOKEN_FILE}")

    return creds


def do_auth():
    creds = _get_credentials()
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds)
    me = yt.channels().list(part="snippet", mine=True).execute()
    name = me["items"][0]["snippet"]["title"] if me.get("items") else "unknown"
    print(f"\n  ✓ Authorized as: {name}")
    print(f"  Token saved to {TOKEN_FILE}")


# ── Cover image generation ────────────────────────────────────────────────────

def _make_cover(set_name, set_dir):
    """Generate a minimal cover image with ffmpeg if no cover provided."""
    cover_path = os.path.join(set_dir, "_cover.png")
    if os.path.exists(cover_path):
        return cover_path

    # Dark background + set name as text
    title = set_name.upper().replace("_", " ")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x0a0a0a:s=1280x720:r=1",
        "-vf", (
            f"drawtext=text='{title}':fontcolor=white:fontsize=64:"
            f"x=(w-text_w)/2:y=(h-text_h)/2,"
            f"drawtext=text='DJ SET':fontcolor=0x888888:fontsize=32:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+90"
        ),
        "-frames:v", "1",
        cover_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback: plain black frame
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1",
            "-frames:v", "1", cover_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    return cover_path


# ── MP3 → MP4 conversion ──────────────────────────────────────────────────────

def _mp3_to_mp4(mp3_path, cover_path, out_path):
    """Wrap MP3 + static cover image into an MP4 for YouTube upload."""
    print(f"  Converting MP3 → MP4 (this takes a few minutes for long mixes)...")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", cover_path,
        "-i", mp3_path,
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
        "-crf", "28",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print("  ffmpeg error:", result.stderr.decode()[-500:])
        sys.exit(1)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"  ✓ MP4 ready: {out_path}  ({size_mb:.0f} MB)")


# ── Metadata from SET_NOTES.txt ───────────────────────────────────────────────

def _load_metadata(set_dir):
    notes_path = os.path.join(set_dir, "SET_NOTES.txt")
    if not os.path.exists(notes_path):
        return None

    with open(notes_path) as f:
        text = f.read()

    lines = [l for l in text.split("\n") if l.strip()]
    title = lines[0].strip()

    # Creative paragraph = everything before ── TRACKLIST
    desc_lines = []
    tracklist_lines = []
    in_tracklist = False
    for line in lines[1:]:
        if "── TRACKLIST" in line or "── HARMONIC" in line:
            in_tracklist = True
        if in_tracklist:
            tracklist_lines.append(line)
        elif line.strip() and not line.startswith("A DJ set"):
            desc_lines.append(line.strip())

    description = " ".join(desc_lines)

    # Full tracklist for YouTube description
    tracklist_text = "\n".join(tracklist_lines)
    full_description = f"{description}\n\n{tracklist_text}\n\n#DeepHouse #DJSet #MelodicHouse"

    tags = ["Deep House", "Melodic House", "DJ Mix", "Electronic Music",
            "Melodic Techno", "House Music", "DJ Set"]

    return {"title": title, "description": full_description, "tags": tags}


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_set(set_dir, cover_path=None):
    mp3 = os.path.join(set_dir, "FULL_SET.mp3")
    if not os.path.exists(mp3):
        print(f"  ERROR: FULL_SET.mp3 not found in {set_dir}")
        sys.exit(1)

    meta = _load_metadata(set_dir)
    if meta is None:
        print(f"  ERROR: SET_NOTES.txt not found in {set_dir}")
        sys.exit(1)

    set_name = os.path.basename(set_dir.rstrip("/"))

    print(f"\n  Set:   {meta['title']}")
    print(f"  File:  {mp3}  ({os.path.getsize(mp3)/1e6:.0f} MB)")

    # Cover image
    if not cover_path:
        cover_path = _make_cover(set_name, set_dir)
    print(f"  Cover: {cover_path}")

    # Convert to MP4
    mp4_path = os.path.join(set_dir, "FULL_SET.mp4")
    _mp3_to_mp4(mp3, cover_path, mp4_path)

    # Authenticate
    creds = _get_credentials()
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title":       meta["title"],
            "description": meta["description"],
            "tags":        meta["tags"],
            "categoryId":  "10",   # Music
        },
        "status": {
            "privacyStatus":          "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(mp4_path, mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024)

    print(f"\n  Uploading to YouTube (unlisted)...")
    request = yt.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Uploading... {pct}%", end="\r")

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  ✓ Uploaded! (unlisted)")
    print(f"  URL: {video_url}")

    # Clean up temp MP4
    os.remove(mp4_path)
    print(f"  (temp MP4 removed)")

    return video_url


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload a DJ set to YouTube as unlisted")
    parser.add_argument("--auth",  action="store_true", help="Authorize with your YouTube/Google account")
    parser.add_argument("--set",   metavar="DIR",       help="Path to set folder (FULL_SET.mp3 + SET_NOTES.txt)")
    parser.add_argument("--cover", metavar="IMG",       help="Cover image path (JPG/PNG). Auto-generated if omitted.")
    args = parser.parse_args()

    if args.auth:
        do_auth()
    elif args.set:
        upload_set(args.set, cover_path=args.cover)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
