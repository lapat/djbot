#!/usr/bin/env python3
"""
DJ Kyoko — make a mix from a free-text request.

Usage:
  python make_mix.py "solomun meets madonna"
  python make_mix.py "solomun meets madonna" --minutes 30

Fully automated: an LLM curates real tracks matching your request, each is
validated against YouTube (dropped if not found), downloaded, and mixed
through the same beat-matching/quality-gate engine as build_set.py's
hand-authored brains — mix points are auto-tuned by the engine itself
(mixer/set_builder.py retries mix_in_bars candidates per transition and
keeps whichever passes the phase-error gate), no manual listening required.

Needs ANTHROPIC_API_KEY set for the curation step. Downloads run via
yt-dlp on whatever machine you run this on — works best on a normal
residential connection (see README's note on cloud IPs / YouTube blocking).

This is a personal tool: it builds whatever you ask it to build, the same
way you'd build a mix by hand-curating a brain — you're responsible for
the rights to whatever you have it download and mix. See the main
README's "A note on rights" section.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mixer.curate import curate_and_validate, BillingCapError, ANTHROPIC_URL
from mixer.set_builder import build_full_set

ROOT = Path(__file__).resolve().parent


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "custom_mix"


class _Brain:
    def __init__(self, style_name, set_name, notes, tracks):
        self.STYLE_NAME = style_name
        self.SET_NAME = set_name
        self.SET_NOTES = notes
        self.BPM_RANGE = (60, 200)
        self.CF_BARS = 16
        self.OUTRO_BARS = 90
        self.SNIPPET_SEC = 15
        # Cross-genre "meets" requests naturally have wider tempo gaps than a
        # hand-curated single-genre brain — the default 8% is tuned for the
        # latter. The BPM ramp already handles gradual changes gracefully;
        # this just raises the ceiling before a pair is rejected outright.
        self.MAX_BPM_DIFF_PCT = 15.0
        self.MAX_BODY_SEC_RANGE = (120, 140)  # more frequent transitions than the 180s engine default
        self.SKIP_SNIPPETS = True  # only the full mix matters for this flow
        self.TRACKS = tracks


def _download(video_id: str, dest: Path):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--no-playlist", "--remote-components", "ejs:github",
        "-o", str(dest.with_suffix("")) + ".%(ext)s",
    ]
    url = f"https://www.youtube.com/watch?v={video_id}"
    # YouTube's anti-bot checks reliably 403 an anonymous session even with
    # the JS challenge solver enabled — a real logged-in browser session
    # (via --cookies-from-browser) is what actually gets through. Fall back
    # to no cookies if Chrome isn't installed/usable on this machine.
    result = subprocess.run(
        base_cmd + ["--cookies-from-browser", "chrome", url],
        capture_output=True, text=True, timeout=180,
    )
    if not dest.exists():
        result = subprocess.run(
            base_cmd + [url], capture_output=True, text=True, timeout=180,
        )
    if not dest.exists():
        raise RuntimeError(f"yt-dlp failed for {video_id}:\n{result.stdout}\n{result.stderr}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("request", help='free-text request, e.g. "solomun meets madonna"')
    parser.add_argument("--minutes", type=float, default=30.0, help="rough target length (default 30)")
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set (needed for track curation).")
        sys.exit(1)
    base_url = os.environ.get("ANTHROPIC_BASE_URL", ANTHROPIC_URL)

    n_tracks = max(3, round(args.minutes / 3.2))
    slug = _slugify(args.request)

    print(f"\n  Curating ~{n_tracks} tracks for: {args.request!r}")
    try:
        validated = curate_and_validate(args.request, n_tracks, api_key, args.model, base_url)
    except BillingCapError as e:
        print(f"DJBOT_ERROR: BILLING_CAP\n{e}")
        sys.exit(3)
    if len(validated) < 2:
        print(f"  Only found {len(validated)} usable track(s) — need at least 2. Try a different request.")
        sys.exit(1)

    print(f"  {len(validated)}/{n_tracks} tracks confirmed on YouTube:")
    for t in validated:
        print(f"    {t['artist']} - {t['title']}  (~{t.get('approx_bpm', '?')} BPM)")

    print(f"\n  Downloading...")
    tracks = []
    for i, t in enumerate(validated):
        dest = ROOT / "downloads" / slug / f"{t['video_id']}.mp3"
        _download(t["video_id"], dest)
        tracks.append({
            "name": f"T{i+1:02d}",
            "label": f"{t['artist']} - {t['title']}",
            "path": str(dest),
            "hint": t.get("approx_bpm"),
        })

    brain = _Brain(
        style_name=slug,
        set_name=slug,
        notes=f'A mix built from the request: "{args.request}"',
        tracks=tracks,
    )
    print(f"\n  Building mix ({len(tracks)} tracks)...\n")
    build_full_set(brain)
    print(f"\n  Done: output/{slug}/FULL_SET.mp3")


if __name__ == "__main__":
    main()
