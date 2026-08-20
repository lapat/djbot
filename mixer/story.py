"""
Optional creative flourishes for a mix: a short narrated "story" about the
set (DJ Kyoko's own voice, not a technical description) plus a creative mix
name, and two AI-generated images via Replicate FLUX — one illustrating that
story, one a portrait of DJ Kyoko herself styled by the request. Both are
best-effort: any failure here returns None rather than raising, so it never
fails the mix itself — the audio is the product, these are garnish.
"""
import json
import re
import time

import requests

REPLICATE_PREDICTIONS_URL = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"

NAMING_SYSTEM_PROMPT = """You are DJ Kyoko, an AI DJ with a vivid imagination. \
Given a mix request and its actual tracklist, invent:
1. A short, evocative NAME for this mix — 2 to 5 words, like a real DJ set or \
album title. Not literally the request text restated, and not generic \
("Vibes Mix") — specific and a little unexpected.
2. A short NARRATIVE — 2 to 4 sentences — that captures the FEELING and \
IMAGERY the set conjures, like a tiny story or scene playing out, not a \
description of the music or a list of the artists. Be specific and visual, \
not generic ("a horse crossing an empty street at 3am" beats "the music \
feels nostalgic").

Return ONLY a JSON object, no prose, no markdown fences:
{"name": "...", "narrative": "..."}"""


def generate_mix_story(request_text: str, tracks: list, api_key: str, model: str, base_url: str):
    """tracks: the job's tracks_state list — dicts with a "label" field
    ("Artist - Title"), not separate artist/title keys. Returns
    {"name": str, "narrative": str} or None on any failure."""
    track_list = "; ".join(t.get("label", "") for t in tracks[:6] if t.get("label"))
    resp = requests.post(
        base_url,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": model, "max_tokens": 400,
            "thinking": {"type": "disabled"},
            "system": NAMING_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f'Request: "{request_text}"\nTracklist: {track_list}'}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    parsed = json.loads(text)
    name = (parsed.get("name") or "").strip()
    narrative = (parsed.get("narrative") or "").strip()
    if not name or not narrative:
        return None
    return {"name": name, "narrative": narrative}


TRACK_INTROS_SYSTEM_PROMPT = """You are DJ Kyoko, an AI DJ voicing your own live radio-style \
set. You already invented an overall NAME and NARRATIVE for this mix — use them as \
continuity and flavor, don't just repeat the narrative verbatim for every track.

For EACH track in the tracklist below, write a short (2 to 3 sentence) spoken DJ intro — \
the kind of thing you'd say live as that track's own quiet musical intro plays underneath \
you, like a real radio DJ talking as the next song fades in. Reference that track's actual \
title and artist by name. Let the mix's overall story/narrative give each intro some \
flavor and continuity with the rest of the set (recurring imagery, mood, or a throughline) \
so the whole set feels like one cohesive night, not disconnected trivia read per song.

Keep sentences short and natural to SAY OUT LOUD — this gets read by a text-to-speech \
voice, not read on a page. No hashtags, no emoji, no stage directions or parenthetical \
notes, no "Track N" labels, no literal timestamps.

Return ONLY a JSON object, no prose, no markdown fences — one string per track, in the \
EXACT same order as the tracklist given:
{"intros": ["...", "...", ...]}"""


def generate_track_intros(request_text: str, mix_name: str, narrative: str, tracks: list,
                           api_key: str, model: str, base_url: str) -> list[str] | None:
    """tracks: dicts with a "label" field ("Artist - Title"), in play order.
    Returns a list of intro strings (same length/order as tracks), or None
    on any failure — best-effort creative flourish, same philosophy as
    generate_mix_story: never worth failing the mix build over."""
    if not tracks:
        return None
    track_list = "\n".join(f"{i+1}. {t.get('label', '')}" for i, t in enumerate(tracks))
    resp = requests.post(
        base_url,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": model, "max_tokens": 1500,
            "thinking": {"type": "disabled"},
            "system": TRACK_INTROS_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": (
                f'Mix request: "{request_text}"\n'
                f'Mix name: "{mix_name}"\n'
                f'Mix narrative: "{narrative}"\n'
                f'Tracklist (in play order):\n{track_list}'
            )}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    parsed = json.loads(text)
    intros = parsed.get("intros")
    if not isinstance(intros, list) or len(intros) != len(tracks):
        return None
    intros = [str(x).strip() for x in intros]
    if not all(intros):
        return None
    return intros


def _flux_image(prompt: str, replicate_token: str, timeout: int = 90) -> str | None:
    resp = requests.post(
        REPLICATE_PREDICTIONS_URL,
        headers={
            "Authorization": f"Bearer {replicate_token}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        },
        json={"input": {"prompt": prompt, "aspect_ratio": "16:9", "output_format": "jpg"}},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    # "Prefer: wait" is a request, not a guarantee — confirmed live (2026-08-19):
    # Replicate can still return HTTP 202 with status="processing" and
    # output=null immediately, rather than blocking until the prediction
    # actually finishes. Trusting the initial response's "output" field
    # silently returned None every time this happened — no exception, no
    # error logged, just a missing image with zero trace. Poll the
    # prediction's own status URL until it actually reaches a terminal
    # state, then read output from THAT response instead.
    poll_url = data.get("urls", {}).get("get")
    deadline = time.monotonic() + timeout
    while data.get("status") not in ("succeeded", "failed", "canceled"):
        if not poll_url or time.monotonic() >= deadline:
            return None
        time.sleep(1.5)
        poll_resp = requests.get(poll_url, headers={"Authorization": f"Bearer {replicate_token}"}, timeout=15)
        poll_resp.raise_for_status()
        data = poll_resp.json()

    if data.get("status") != "succeeded":
        return None
    output = data.get("output")
    if isinstance(output, list) and output:
        return output[0]
    if isinstance(output, str) and output:
        return output
    return None


def generate_story_image(narrative: str, replicate_token: str) -> str | None:
    prompt = f"Cinematic, atmospheric scene: {narrative}. Film photography style, dramatic lighting, no text."
    return _flux_image(prompt, replicate_token)


def generate_dj_portrait(request_text: str, replicate_token: str) -> str | None:
    prompt = (
        f'Portrait of a stylish AI DJ named Kyoko, mid-performance in a DJ booth, visually '
        f'inspired by the mood/era/style of "{request_text}" — let that influence her outfit, '
        f'the lighting, and the setting. Dynamic pose, dramatic lighting, high detail, no text.'
    )
    return _flux_image(prompt, replicate_token)
