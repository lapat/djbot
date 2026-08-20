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


class BillingCapError(Exception):
    """Raised when the API key has hit a spend cap / credit limit / rate limit."""

CURATION_SYSTEM_PROMPT = """You curate tracklists for an automated beat-matching \
DJ mixing engine. Given a request describing one or more artists/styles, return \
a JSON array of REAL, EXISTING tracks (or real remixes/edits/covers) that could \
plausibly be beat-mixed together into one cohesive set true to the request.

When the request names specific artists (e.g. "X meets Y"), treat those artists \
as reference points for the sound/vibe, NOT as the only two artists allowed in \
the set. Build a broader blend: include real tracks from OTHER artists in a \
similar style, era, or genre alongside the named ones, so the set sounds like a \
real DJ set inspired by X and Y rather than a two-artist mixtape. Include at \
least one or two tracks from each named artist, but no single artist — named or \
otherwise — should ever account for more than half the tracklist. For a 6-track \
set that means at most 3 tracks from any one artist; for a 3-4 track set, at \
most 1 from any one artist — the shorter the set, the more every track needs \
to pull its own weight toward variety.

A "X meets Y" request has TWO halves, and BOTH must show up in the actual \
tracklist you return, not just the one that's easier. This applies just as much \
when a half is a time period, scene, or vibe ("2026 club bangers", "underground", \
"summer") as when it's a named artist — before finalizing your answer, check: \
does this list contain real tracks that genuinely represent EACH half, not just \
the half you're more confident has famous, easy-to-verify tracks? If one half is \
recent or obscure and you're unsure of exact real titles, still make a real, \
good-faith effort at real tracks for it — don't quietly substitute more of the \
easy half instead.

Never put two tracks by the same artist back-to-back in the list you return — \
spread each artist's tracks out across the set. This matters even more than \
usual for "X meets Y" requests, since clustering every X track together and \
every Y track together defeats the point of a blended set.

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


def curate_tracklist(request_text: str, n_tracks: int, api_key: str, model: str = DEFAULT_MODEL,
                      base_url: str = ANTHROPIC_URL) -> list:
    """Ask Claude for n_tracks real tracks matching request_text. Returns a
    list of {"artist":..., "title":..., "approx_bpm":...} dicts (unvalidated).

    base_url defaults to the real Anthropic API, but can point at a proxy
    (e.g. a spend-capped relay) instead — the request/response shape and
    the x-api-key header are unchanged either way."""
    resp = requests.post(
        base_url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            # Sonnet 5 runs adaptive thinking by default, and thinking tokens
            # count against max_tokens — for a deterministic JSON-list task
            # like this there's nothing to think through, so disabling it
            # keeps the full budget available for the actual output instead
            # of leaving JSON truncation risk dependent on how much the model
            # happens to "think" for a given request.
            "thinking": {"type": "disabled"},
            "system": CURATION_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": f'Request: "{request_text}"\nReturn exactly {n_tracks} tracks.'}
            ],
        },
        timeout=60,
    )
    if resp.status_code == 429:
        raise BillingCapError(resp.text)
    if resp.status_code in (400, 403):
        low = resp.text.lower()
        if any(kw in low for kw in ("credit balance", "spend limit", "budget", "quota", "billing")):
            raise BillingCapError(resp.text)
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


def _spread_same_artist(tracks: list) -> list:
    """Greedily reorder so no two adjacent tracks share an artist, without
    disturbing the overall BPM-ascending arc more than necessary. The model
    is asked not to cluster artists, but that's a request, not a guarantee —
    the BPM sort that runs right before this can also re-cluster tracks that
    happen to share a similar tempo, so this pass is the actual enforcement.

    Searches forward first (preserves the BPM arc better), then backward if
    forward finds nothing — a collision at the very last position has no
    forward candidate by definition, so forward-only search can never fix
    it (confirmed by a real test failure: two same-artist tracks left
    adjacent at the tail of a 6-track list). If an artist accounts for more
    than half the tracklist, no reordering can avoid every adjacency — that
    case is a curation-diversity problem, not something this pass can fix."""
    tracks = list(tracks)
    n = len(tracks)
    for i in range(1, n):
        prev_artist = tracks[i - 1].get("artist", "").strip().lower()
        if tracks[i].get("artist", "").strip().lower() != prev_artist:
            continue
        swapped = False
        for j in range(i + 1, n):
            if tracks[j].get("artist", "").strip().lower() != prev_artist:
                tracks[i], tracks[j] = tracks[j], tracks[i]
                swapped = True
                break
        if not swapped:
            for j in range(i - 2, -1, -1):
                if tracks[j].get("artist", "").strip().lower() != prev_artist:
                    tracks[i], tracks[j] = tracks[j], tracks[i]
                    break
    return tracks


def curate_and_validate(request_text: str, n_tracks: int, api_key: str, model: str = DEFAULT_MODEL,
                         base_url: str = ANTHROPIC_URL) -> list:
    """Curate then validate against YouTube, dropping any track that can't be
    found, then sort by approx_bpm ascending (lower-energy opener first) to
    reduce the odds of a jarring adjacent BPM jump, then spread out same-artist
    tracks so the set doesn't cluster one artist's songs back-to-back."""
    candidates = curate_tracklist(request_text, n_tracks, api_key, model, base_url)
    validated = []
    for t in candidates:
        vid = find_youtube_id(t["artist"], t["title"])
        if vid:
            validated.append({**t, "video_id": vid})
        else:
            print(f"  [skip] could not find on YouTube: {t.get('artist')} - {t.get('title')}")
    validated.sort(key=lambda t: t.get("approx_bpm") or 999)
    validated = _spread_same_artist(validated)
    return validated
