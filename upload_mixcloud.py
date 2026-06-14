"""
Upload a DJ set to Mixcloud.

One-time setup:
  1. Go to https://www.mixcloud.com/developers/ → Create App
  2. Set Redirect URI to: http://localhost:8765/callback
  3. Copy your Client ID and Client Secret
  4. Run: python upload_mixcloud.py --auth
     (opens browser, you approve, token is saved to .mixcloud_token)
  5. Run: python upload_mixcloud.py --set output/hours_before_light/

Usage:
  python upload_mixcloud.py --auth
  python upload_mixcloud.py --set output/hours_before_light/ [--private]
"""
import argparse, json, os, sys, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import requests

TOKEN_FILE  = ".mixcloud_token"
CLIENT_FILE = ".mixcloud_app"   # stores client_id + client_secret
REDIRECT    = "http://localhost:8765/callback"
AUTH_URL    = "https://www.mixcloud.com/oauth/authorize"
TOKEN_URL   = "https://www.mixcloud.com/oauth/access_token"
API_BASE    = "https://api.mixcloud.com"


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def _load_app():
    if not os.path.exists(CLIENT_FILE):
        print("\nNo app credentials found. Run setup first:\n")
        print("  1. Go to https://www.mixcloud.com/developers/")
        print("  2. Click 'Create App'")
        print("  3. Set Redirect URI to:", REDIRECT)
        print("  4. Run: python upload_mixcloud.py --auth\n")
        sys.exit(1)
    with open(CLIENT_FILE) as f:
        return json.load(f)


def _save_app(client_id, client_secret):
    with open(CLIENT_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f)
    print(f"  Saved app credentials to {CLIENT_FILE}")


def _load_token():
    if not os.path.exists(TOKEN_FILE):
        print("No token found. Run: python upload_mixcloud.py --auth")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        return json.load(f)["access_token"]


def _save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token}, f)
    print(f"  Token saved to {TOKEN_FILE}")


def do_auth():
    """Interactive OAuth2 flow — opens browser, captures callback locally."""
    # Collect client credentials if not saved
    if not os.path.exists(CLIENT_FILE):
        print("\n── Mixcloud App Setup ───────────────────────────────────")
        print("Go to https://www.mixcloud.com/developers/ and create an app.")
        print(f"Set Redirect URI to: {REDIRECT}\n")
        client_id     = input("Paste your Client ID:     ").strip()
        client_secret = input("Paste your Client Secret: ").strip()
        _save_app(client_id, client_secret)
    else:
        app = _load_app()
        client_id     = app["client_id"]
        client_secret = app["client_secret"]

    # Build auth URL
    params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT,
        "response_type": "code",
    }
    auth_url = AUTH_URL + "?" + urlencode(params)
    print(f"\n  Opening browser for Mixcloud authorization...")
    webbrowser.open(auth_url)

    # Local HTTP server to capture the callback
    code_holder = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            code = qs.get("code", [None])[0]
            if code:
                code_holder["code"] = code
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<h2>No code received.</h2>")

        def log_message(self, *_):
            pass   # silence server logs

    print("  Waiting for authorization callback on port 8765...")
    server = HTTPServer(("localhost", 8765), Handler)
    server.handle_request()

    code = code_holder.get("code")
    if not code:
        print("  ERROR: Did not receive authorization code.")
        sys.exit(1)

    # Exchange code for token
    resp = requests.post(TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT,
        "code":          code,
        "grant_type":    "authorization_code",
    })
    data = resp.json()
    if "access_token" not in data:
        print("  ERROR getting token:", data)
        sys.exit(1)

    _save_token(data["access_token"])
    print("\n  ✓ Authorized! You can now upload sets.")

    # Confirm identity
    me = requests.get(f"{API_BASE}/me/", params={"access_token": data["access_token"]}).json()
    print(f"  Logged in as: {me.get('name')} (@{me.get('username')})")


# ── Set metadata loader ───────────────────────────────────────────────────────

def _load_set_metadata(set_dir):
    """
    Reads SET_NOTES.txt and snippet files to build Mixcloud upload metadata.
    Returns dict with: name, description, tags, sections (tracklist chapters).
    """
    notes_path = os.path.join(set_dir, "SET_NOTES.txt")
    if not os.path.exists(notes_path):
        return None

    with open(notes_path) as f:
        text = f.read()

    lines = text.strip().split("\n")
    # First non-empty line = set name
    name = lines[0].strip()
    # Description = creative paragraph (everything up to ── TRACKLIST)
    desc_lines = []
    tracklist_lines = []
    in_tracklist = False
    for line in lines[2:]:
        if "── TRACKLIST" in line or "── HARMONIC" in line:
            in_tracklist = True
            continue
        if in_tracklist:
            tracklist_lines.append(line)
        else:
            desc_lines.append(line)

    description = " ".join(l.strip() for l in desc_lines if l.strip())

    # Parse tracklist for section timestamps
    # We'll estimate timestamps from average track duration
    # (Mixcloud sections are just timestamps + artist + song name)
    sections = []
    current_sec = 0
    avg_track_duration_min = 7.0   # rough estimate; we'll use snippet positions
    for line in tracklist_lines:
        line = line.strip()
        if not line or line.startswith("──"):
            continue
        # Format: "  01  Artist — Track Title   KEY  BPM  mood"
        parts = line.split("  ")
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            try:
                idx = int(parts[0])
                rest = parts[1]
                # Split "Artist — Track" on em-dash
                if "—" in rest:
                    artist, song = rest.split("—", 1)
                    artist = artist.strip()
                    song   = song.split("  ")[0].strip()   # drop key/bpm info
                    sections.append({
                        "artist":    artist,
                        "song":      song,
                        "start_time": current_sec,
                    })
                    current_sec += int(avg_track_duration_min * 60)
            except (ValueError, IndexError):
                pass

    # Tags (Mixcloud allows up to 5)
    tags = ["Deep House", "Melodic House", "Melodic Techno", "Electronic", "DJ Mix"]

    return {
        "name":        name,
        "description": description,
        "tags":        tags,
        "sections":    sections,
    }


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_set(set_dir, private=False):
    token  = _load_token()
    mp3    = os.path.join(set_dir, "FULL_SET.mp3")
    if not os.path.exists(mp3):
        print(f"  ERROR: FULL_SET.mp3 not found in {set_dir}")
        sys.exit(1)

    meta = _load_set_metadata(set_dir)
    if meta is None:
        print("  ERROR: SET_NOTES.txt not found in", set_dir)
        sys.exit(1)

    print(f"\n  Uploading: {meta['name']}")
    print(f"  File:      {mp3}  ({os.path.getsize(mp3)/1e6:.1f} MB)")
    print(f"  Tags:      {', '.join(meta['tags'])}")
    print(f"  Sections:  {len(meta['sections'])} tracks")
    print(f"  Visibility: {'private' if private else 'public'}\n")

    # Build multipart form fields
    fields = {
        "name":        (None, meta["name"]),
        "description": (None, meta["description"]),
        "publish":     (None, "0" if private else "1"),
        "disable_comments": (None, "0"),
    }

    # Tags: tag-0-tag, tag-1-tag, ...
    for i, tag in enumerate(meta["tags"][:5]):
        fields[f"tags-{i}-tag"] = (None, tag)

    # Sections (tracklist chapters): sections-N-artist, sections-N-song, sections-N-start_time
    for i, sec in enumerate(meta["sections"]):
        fields[f"sections-{i}-artist"]     = (None, sec["artist"])
        fields[f"sections-{i}-song"]       = (None, sec["song"])
        fields[f"sections-{i}-start_time"] = (None, str(sec["start_time"]))

    # The audio file
    file_size = os.path.getsize(mp3)
    print(f"  Uploading {file_size/1e6:.1f} MB to Mixcloud...")

    with open(mp3, "rb") as audio:
        files = dict(fields)
        files["mp3"] = (os.path.basename(mp3), audio, "audio/mpeg")

        resp = requests.post(
            f"{API_BASE}/me/cloudcast/",
            params={"access_token": token},
            files=files,
        )

    data = resp.json()
    if resp.status_code == 200 and "result" in data and data["result"].get("success"):
        url = f"https://www.mixcloud.com{data.get('result', {}).get('key', '')}"
        print(f"\n  ✓ Uploaded successfully!")
        print(f"  URL: {url}")
        return url
    else:
        print(f"\n  ERROR uploading: {resp.status_code}")
        print(json.dumps(data, indent=2))
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload a DJ set to Mixcloud")
    parser.add_argument("--auth",    action="store_true", help="Authorize this app with your Mixcloud account")
    parser.add_argument("--set",     metavar="DIR",       help="Path to set folder (contains FULL_SET.mp3 + SET_NOTES.txt)")
    parser.add_argument("--private", action="store_true", help="Upload as private (unlisted)")
    args = parser.parse_args()

    if args.auth:
        do_auth()
    elif args.set:
        upload_set(args.set, private=args.private)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
