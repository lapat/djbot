"""
Upload a DJ set to Mixcloud.

Usage:
  python scripts/mixcloud_upload.py solomun
  python scripts/mixcloud_upload.py luno
  python scripts/mixcloud_upload.py afterlife

First run: opens a browser for OAuth login, saves the token to
~/.mixcloud_token so you only do that once.

Requires:
  pip install requests

Setup (one-time):
  1. Go to https://www.mixcloud.com/developers/ → Create App
  2. Set the Redirect URI to: http://localhost:8888/callback
  3. Copy your Client ID and Client Secret
  4. Export them (or add to ~/.zshrc):
       export MIXCLOUD_CLIENT_ID="your_client_id"
       export MIXCLOUD_CLIENT_SECRET="your_client_secret"
"""

import os
import sys
import re
import json
import time
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

REDIRECT_URI  = "http://localhost:8888/callback"
TOKEN_FILE    = Path.home() / ".mixcloud_token"
UPLOAD_URL    = "https://api.mixcloud.com/upload/"
AUTH_URL      = "https://www.mixcloud.com/oauth/authorize"
TOKEN_URL     = "https://www.mixcloud.com/oauth/access_token"

# ── Set metadata — maps set name → output dir and display info ────────────────

SETS = {
    "solomun": {
        "dir":   "output/sorry_i_am_late",
        "title": "Sorry I Am Late — Solomun Style Mix",
        "tags":  ["melodic techno", "deep house", "solomun", "mix"],
    },
    "luno": {
        "dir":   "output/hours_before_light",
        "title": "The Hours Before Light — Melodic House Mix",
        "tags":  ["melodic house", "deep house", "luno", "mix"],
    },
    "afterlife": {
        "dir":   "output/pale_transmissions",
        "title": "Pale Transmissions — Afterlife Style Mix",
        "tags":  ["melodic techno", "afterlife", "dark techno", "mix"],
    },
}

# ── OAuth ─────────────────────────────────────────────────────────────────────

_oauth_code = None

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _oauth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _oauth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Error: no code in redirect.</h2>")

    def log_message(self, *args):
        pass  # silence request logs


def _get_access_token(client_id, client_secret):
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        # Quick check the token is still valid
        r = requests.get(f"https://api.mixcloud.com/me/?access_token={token}", timeout=10)
        if r.status_code == 200:
            print(f"  Using saved token (logged in as {r.json().get('name','?')})")
            return token
        print("  Saved token expired, re-authorizing...")

    auth_params = urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
    })
    url = f"{AUTH_URL}?{auth_params}"
    print(f"\n  Opening browser for Mixcloud login...")
    webbrowser.open(url)

    # Local server catches the OAuth redirect
    server = HTTPServer(("localhost", 8888), _CallbackHandler)
    server.timeout = 120
    print("  Waiting for authorization (you have 2 minutes)...")
    while _oauth_code is None:
        server.handle_request()
    server.server_close()

    # Exchange code for token
    r = requests.get(TOKEN_URL, params={
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
        "code":          _oauth_code,
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token exchange failed: {data}")

    token = data["access_token"]
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    print(f"  Token saved to {TOKEN_FILE}")
    return token


# ── Parse SET_NOTES.txt ───────────────────────────────────────────────────────

def _mm_ss_to_seconds(ts):
    """'03:00' → 180"""
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def _parse_set_notes(notes_path):
    """
    Returns:
      description: str  (the narrative block before TRACKLIST)
      tracklist:   list of {"artist": str, "song": str, "start_sec": int}
    """
    text = Path(notes_path).read_text()

    # Description: everything before the TRACKLIST line
    desc_match = re.split(r"── TRACKLIST", text, maxsplit=1)
    description = desc_match[0].strip()

    # Cue sheet entries: "MM:SS–MM:SS  [NN] → Artist - Track"
    # First track: "MM:SS        Set starts — Artist - Track"
    tracklist = []

    # First track (starts at 00:00)
    first = re.search(r"(\d{2}:\d{2})\s+Set starts — (.+)", text)
    if first:
        artist_song = first.group(2).strip()
        # Split on " - " for artist/song; if not present, use whole string as song
        parts = artist_song.split(" - ", 1)
        tracklist.append({
            "artist":    parts[0].strip() if len(parts) == 2 else "",
            "song":      parts[1].strip() if len(parts) == 2 else artist_song,
            "start_sec": 0,
        })

    # Subsequent tracks from cue sheet: "MM:SS–MM:SS  [NN] → Artist - Track"
    for m in re.finditer(r"(\d{2}:\d{2})–\d{2}:\d{2}\s+\[\d+\] → (.+)", text):
        start_sec   = _mm_ss_to_seconds(m.group(1))
        artist_song = m.group(2).strip()
        parts = artist_song.split(" - ", 1)
        tracklist.append({
            "artist":    parts[0].strip() if len(parts) == 2 else "",
            "song":      parts[1].strip() if len(parts) == 2 else artist_song,
            "start_sec": start_sec,
        })

    return description, tracklist


# ── Upload ────────────────────────────────────────────────────────────────────

def upload(set_name, access_token):
    meta      = SETS[set_name]
    set_dir   = Path(meta["dir"])
    mp3_path  = set_dir / "FULL_SET.mp3"
    notes_path = set_dir / "SET_NOTES.txt"

    if not mp3_path.exists():
        raise FileNotFoundError(f"No FULL_SET.mp3 at {mp3_path} — build the set first.")

    description, tracklist = _parse_set_notes(notes_path)

    print(f"\n  Title:       {meta['title']}")
    print(f"  File:        {mp3_path}  ({mp3_path.stat().st_size / 1e6:.0f} MB)")
    print(f"  Tracks:      {len(tracklist)}")
    for t in tracklist:
        m, s = divmod(t["start_sec"], 60)
        print(f"    {m:02d}:{s:02d}  {t['artist']} – {t['song']}")

    # Build multipart fields
    # Mixcloud caps description at 1000 chars
    if len(description) > 1000:
        description = description[:997] + "..."

    data = {
        "name":        meta["title"],
        "description": description,
        "publish":     "1",
    }
    for i, tag in enumerate(meta["tags"]):
        data[f"tags-{i}-tag"] = tag

    for i, t in enumerate(tracklist):
        data[f"tracklist-{i}-artist"]     = t["artist"]
        data[f"tracklist-{i}-song"]       = t["song"]
        data[f"tracklist-{i}-start_time"] = str(t["start_sec"])

    print(f"\n  Uploading to Mixcloud... (this takes a minute for large files)")
    with open(mp3_path, "rb") as f:
        r = requests.post(
            f"{UPLOAD_URL}?access_token={access_token}",
            data=data,
            files={"mp3": (mp3_path.name, f, "audio/mpeg")},
            timeout=600,
        )

    if r.status_code == 200:
        result = r.json()
        slug   = result.get("result", {}).get("key", "")
        url    = f"https://www.mixcloud.com{slug}" if slug else "(check your Mixcloud profile)"
        print(f"\n  ✓ Uploaded!")
        print(f"  URL: {url}")
        return url
    else:
        print(f"\n  ✗ Upload failed: {r.status_code}")
        print(f"  {r.text}")
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SETS:
        print(f"\nUsage: python scripts/mixcloud_upload.py [{' | '.join(SETS)}]\n")
        sys.exit(1)

    set_name = sys.argv[1]

    client_id     = os.environ.get("MIXCLOUD_CLIENT_ID")
    client_secret = os.environ.get("MIXCLOUD_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("\nError: set MIXCLOUD_CLIENT_ID and MIXCLOUD_CLIENT_SECRET env vars.")
        print("  Get them at: https://www.mixcloud.com/developers/")
        print("  Set redirect URI to: http://localhost:8888/callback")
        sys.exit(1)

    print(f"\n  Mixcloud upload — {set_name}")
    token = _get_access_token(client_id, client_secret)
    upload(set_name, token)


if __name__ == "__main__":
    main()
