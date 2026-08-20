"""
Upload a DJ Kyoko set to SoundCloud.

Usage:
  python scripts/soundcloud_upload.py solomun
  python scripts/soundcloud_upload.py solomun --private   # unlisted, for testing

Works with any brain in brains/ — reads SET_NAME/STYLE_NAME from the brain
module and the narrative + cue sheet from output/<SET_NAME>/SET_NOTES.txt,
same convention as scripts/mixcloud_upload.py.

Requires a SoundCloud "Artist Pro" account and an approved API app — as of
2026 SoundCloud reopened developer registration but still gates it behind
manual review (ask their "Otto" assistant at developers.soundcloud.com).
If you don't have API access yet, upload the FULL_SET.mp3 manually — the
mixing/build pipeline works fully without this step.

Setup (one-time):
  1. https://developers.soundcloud.com/ → register an app (Artist Pro required)
  2. Set the redirect URI to: http://localhost:8890/callback
  3. export SOUNDCLOUD_CLIENT_ID="..."
     export SOUNDCLOUD_CLIENT_SECRET="..."

First run opens a browser for OAuth (2.1 + PKCE) login and caches the
token to ~/.soundcloud_token.json so you only authorize once.
"""

import argparse
import base64
import hashlib
import importlib
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

REDIRECT_URI = "http://localhost:8890/callback"
TOKEN_FILE   = Path.home() / ".soundcloud_token.json"
AUTH_URL     = "https://secure.soundcloud.com/authorize"
TOKEN_URL    = "https://secure.soundcloud.com/oauth/token"
UPLOAD_URL   = "https://api.soundcloud.com/tracks"


# ── PKCE + OAuth ──────────────────────────────────────────────────────────────

def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


_oauth_code = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _oauth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
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
        pass


def _save_tokens(data):
    payload = {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at":    time.time() + data.get("expires_in", 3600) - 60,
    }
    TOKEN_FILE.write_text(json.dumps(payload))
    TOKEN_FILE.chmod(0o600)
    return payload["access_token"]


def get_access_token(client_id=None, client_secret=None):
    """Return a valid access token, refreshing or re-authorizing as needed."""
    client_id     = client_id or os.environ.get("SOUNDCLOUD_CLIENT_ID")
    client_secret = client_secret or os.environ.get("SOUNDCLOUD_CLIENT_SECRET")

    if TOKEN_FILE.exists():
        cached = json.loads(TOKEN_FILE.read_text())
        if cached.get("expires_at", 0) > time.time():
            return cached["access_token"]
        if cached.get("refresh_token") and client_id and client_secret:
            r = requests.post(TOKEN_URL, data={
                "grant_type":    "refresh_token",
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": cached["refresh_token"],
            }, timeout=10)
            if r.status_code == 200:
                print("  Refreshed SoundCloud token.")
                return _save_tokens(r.json())
            print("  Refresh failed, re-authorizing...")

    if not client_id or not client_secret:
        raise RuntimeError(
            "No cached SoundCloud token and SOUNDCLOUD_CLIENT_ID/SECRET not set. "
            "See setup instructions at the top of this file."
        )

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    auth_params = urllib.parse.urlencode({
        "client_id":             client_id,
        "redirect_uri":          REDIRECT_URI,
        "response_type":         "code",
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "state":                 state,
    })
    print("\n  Opening browser for SoundCloud login...")
    webbrowser.open(f"{AUTH_URL}?{auth_params}")

    server = HTTPServer(("localhost", 8890), _CallbackHandler)
    server.timeout = 180
    print("  Waiting for authorization (you have 3 minutes)...")
    global _oauth_code
    _oauth_code = None
    while _oauth_code is None:
        server.handle_request()
    server.server_close()

    r = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
        "code":          _oauth_code,
        "code_verifier": verifier,
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token exchange failed: {data}")
    print(f"  Token saved to {TOKEN_FILE}")
    return _save_tokens(data)


# ── Parse SET_NOTES.txt (same cue-sheet format as scripts/mixcloud_upload.py) ─

def _mm_ss_to_seconds(ts):
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def _parse_set_notes(notes_path):
    text = Path(notes_path).read_text()
    description = re.split(r"── TRACKLIST", text, maxsplit=1)[0].strip()

    tracklist = []
    first = re.search(r"(\d{2}:\d{2})\s+Set starts — (.+)", text)
    if first:
        parts = first.group(2).strip().split(" - ", 1)
        tracklist.append({
            "artist": parts[0].strip() if len(parts) == 2 else "",
            "song":   parts[1].strip() if len(parts) == 2 else first.group(2).strip(),
            "start_sec": 0,
        })
    for m in re.finditer(r"(\d{2}:\d{2})–\d{2}:\d{2}\s+\[\d+\] → (.+)", text):
        parts = m.group(2).strip().split(" - ", 1)
        tracklist.append({
            "artist": parts[0].strip() if len(parts) == 2 else "",
            "song":   parts[1].strip() if len(parts) == 2 else m.group(2).strip(),
            "start_sec": _mm_ss_to_seconds(m.group(1)),
        })
    return description, tracklist


# ── Upload ────────────────────────────────────────────────────────────────────

def upload(brain_name, access_token, publish=True):
    """Upload output/<SET_NAME>/FULL_SET.mp3 for the given brain. Returns the track URL."""
    brain = importlib.import_module(f"brains.{brain_name}")
    set_dir    = ROOT / "output" / brain.SET_NAME
    mp3_path   = set_dir / "FULL_SET.mp3"
    notes_path = set_dir / "SET_NOTES.txt"

    if not mp3_path.exists():
        raise FileNotFoundError(f"No FULL_SET.mp3 at {mp3_path} — build the set first.")

    title = f"{brain.SET_NAME.replace('_', ' ').title()} — DJ Kyoko x {brain.STYLE_NAME.title()} Style Mix"
    description, tracklist = "", []
    if notes_path.exists():
        description, tracklist = _parse_set_notes(notes_path)

    tracklist_lines = []
    for t in tracklist:
        h, rem = divmod(t["start_sec"], 3600)
        m, s = divmod(rem, 60)
        tracklist_lines.append(f"{t['artist'] or 'Unknown'} – {t['song']} – {h:02d}:{m:02d}:{s:02d}")
    combined = f"{description}\n\n" + "\n".join(tracklist_lines)
    if len(combined) > 4000:
        combined = combined[:3997] + "..."

    print(f"\n  Title:   {title}")
    print(f"  File:    {mp3_path}  ({mp3_path.stat().st_size / 1e6:.0f} MB)")
    print(f"  Tracks:  {len(tracklist)}")
    print(f"  Sharing: {'public' if publish else 'private'}")

    cover_path = next(
        (p for p in [ROOT / "output/artwork" / f"{brain.SET_NAME}_cover.jpg"] if p.exists()),
        None,
    )

    data = {
        "track[title]":       title,
        "track[description]": combined,
        "track[sharing]":     "public" if publish else "private",
        "track[genre]":       getattr(brain, "STYLE_NAME", "electronic"),
    }
    files = {"track[asset_data]": (mp3_path.name, open(mp3_path, "rb"), "audio/mpeg")}
    if cover_path:
        files["track[artwork_data]"] = (cover_path.name, open(cover_path, "rb"), "image/jpeg")

    print("\n  Uploading to SoundCloud... (large files take a few minutes)")
    try:
        r = requests.post(
            UPLOAD_URL,
            headers={"Authorization": f"OAuth {access_token}"},
            data=data,
            files=files,
            timeout=1200,
        )
    finally:
        for fh in files.values():
            fh[1].close()

    if r.status_code in (200, 201):
        result = r.json()
        url = result.get("permalink_url", "(check your SoundCloud profile)")
        print(f"\n  ✓ Uploaded!\n  URL: {url}")
        return url

    print(f"\n  ✗ Upload failed: {r.status_code}\n  {r.text}")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("brain", help="brain name, e.g. solomun (must match brains/<name>.py)")
    parser.add_argument("--private", action="store_true", help="upload as unlisted, not public")
    args = parser.parse_args()

    print(f"\n  SoundCloud upload — {args.brain}")
    token = get_access_token()
    upload(args.brain, token, publish=not args.private)


if __name__ == "__main__":
    main()
