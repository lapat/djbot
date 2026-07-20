"""
LLM-based track curation for make_mix.py.

Turns a free-text request like "solomun meets madonna" into a validated,
buildable tracklist: asks Claude for real tracks blending the requested
artists/styles, then confirms each one actually exists on YouTube via a
metadata-only yt-dlp search (no download) before handing it to the mixer.

The engine itself (mixer/set_builder.py) already auto-retries mix_in_bars
candidates per transition and quality-gates every result — this module only
needs to produce a real, existing, sensibly-ordered tracklist, not tune
anything about how it's mixed.
"""
import json
import re
import subprocess

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"

CURATION_SYSTEM_PROMPT = """You curate tracklists for an automated beat-matching \
DJ mixing engine. Given a request describing one or more artists/styles, return \
a JSON array of REAL, EXISTING tracks (or real remixes/edits/covers) that could \
plausibly be beat-mixed together into one cohesive set true to the request.

Prefer tracks with compatible tempos (roughly within 8% of their neighbors, or \
arranged so tempo changes gradually across the set) — the engine can smoothly \
ramp small BPM differences between adjacent tracks but works best with a \
coherent arc, not random jumps.

If the named artists/styles don't naturally overlap, get creative but stay \
truthful: use real remixes, edits, or covers that bridge them rather than \
inventing a track that doesn't exist. Order the list as a real set: start \
lower-energy/mid-tempo, build, hit a peak, then a slight release near the end.

Return ONLY a JSON array, no prose, no markdown fences. Each entry:
{"artist": "...", "title": "...", "approx_bpm": 122}
"""


def curate_tracklist(request_text: str, n_tracks: int, api_key: str, model: str = DEFAULT_MODEL) -> list:
    """Ask Claude for n_tracks real tracks matching request_text. Returns a
    list of {"artist":..., "title":..., "approx_bpm":...} dicts (unvalidated)."""
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "system": CURATION_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": f'Request: "{request_text}"\nReturn exactly {n_tracks} tracks.'}
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def find_youtube_id(artist: str, title: str, timeout: int = 20):
    """Metadata-only yt-dlp search (no download) — returns a real video ID or None."""
    query = f"ytsearch1:{artist} - {title} audio"
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", "--no-warnings", query],
        capture_output=True, text=True, timeout=timeout,
    )
    lines = result.stdout.strip().splitlines()
    return lines[0] if lines else None


def curate_and_validate(request_text: str, n_tracks: int, api_key: str, model: str = DEFAULT_MODEL) -> list:
    """Curate then validate against YouTube, dropping any track that can't be
    found, then sort by approx_bpm ascending (lower-energy opener first) to
    reduce the odds of a jarring adjacent BPM jump."""
    candidates = curate_tracklist(request_text, n_tracks, api_key, model)
    validated = []
    for t in candidates:
        vid = find_youtube_id(t["artist"], t["title"])
        if vid:
            validated.append({**t, "video_id": vid})
        else:
            print(f"  [skip] could not find on YouTube: {t.get('artist')} - {t.get('title')}")
    validated.sort(key=lambda t: t.get("approx_bpm") or 999)
    return validated
