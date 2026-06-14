"""
Parse DJ mix tracklists from YouTube descriptions and comments.

Handles the most common formats DJs use:
  00:00 Artist - Title
  00:00 - Artist - Title
  1. 00:00 Artist "Title"
  00:00:00 Artist - Title
  [00:00] Artist - Title
  00:00 Title (Artist Remix)
"""
import re
from typing import Optional


# Matches timestamps like 0:00, 00:00, 1:23:45, [00:00], (00:00)
_TS = r"[\[\(]?(\d{1,2}):(\d{2})(?::(\d{2}))?[\]\)]?"

# Full line patterns — timestamp + separator + track info
_PATTERNS = [
    # 00:00 Artist - Title
    re.compile(rf"^(?:\d+[\.\)]\s*)?{_TS}\s*[-–—]?\s*(.+)$", re.MULTILINE),
]


def _ts_to_sec(h_or_m: str, m_or_s: str, s: Optional[str]) -> float:
    if s is not None:
        return int(h_or_m) * 3600 + int(m_or_s) * 60 + int(s)
    return int(h_or_m) * 60 + int(m_or_s)


def _split_artist_title(text: str) -> tuple[str, str]:
    """
    Best-effort split of 'Artist - Title' or 'Title (Artist Remix)' etc.
    Returns (artist, title).
    """
    text = text.strip().strip("-–—").strip()

    # Common separators: ' - ', ' – ', ' — '
    for sep in [" - ", " – ", " — "]:
        if sep in text:
            parts = text.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    # Fallback: whole string is the title, artist unknown
    return "", text


def parse(text: str) -> list[dict]:
    """
    Extract a list of {title, artist, start_sec} dicts from any text block.
    Returns empty list if no timestamps found.
    """
    if not text:
        return []

    entries = []
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            groups = m.groups()
            # Last group is the track text; earlier groups are timestamp parts
            track_text = groups[-1].strip()
            ts_parts   = groups[:-1]

            # Filter out empty / noise lines
            if not track_text or len(track_text) < 3:
                continue
            # Skip lines that look like pure headers (all caps, no separator)
            if track_text.isupper() and " - " not in track_text:
                continue

            start_sec = _ts_to_sec(
                ts_parts[0],
                ts_parts[1],
                ts_parts[2] if len(ts_parts) > 2 else None,
            )
            artist, title = _split_artist_title(track_text)
            entries.append({
                "start_sec": start_sec,
                "artist": artist,
                "title": title,
                "raw": track_text,
            })

    if not entries:
        return []

    # Sort by timestamp, deduplicate
    entries.sort(key=lambda e: e["start_sec"])
    seen = set()
    unique = []
    for e in entries:
        key = (e["start_sec"], e["raw"][:40])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Fill in end_sec = next track's start_sec
    for i, e in enumerate(unique):
        e["end_sec"] = unique[i + 1]["start_sec"] if i + 1 < len(unique) else None

    return unique


def best_tracklist(description: str, comments: list[str]) -> tuple[list[dict], str]:
    """
    Try description first (most reliable), then comments.
    Returns (tracks, source) where source is 'description'|'comment'|'none'.
    """
    tracks = parse(description or "")
    if len(tracks) >= 3:
        return tracks, "description"

    # Try each comment, pick the one with the most tracks
    best, best_src = [], "none"
    for i, c in enumerate(comments or []):
        t = parse(c)
        if len(t) > len(best):
            best, best_src = t, f"comment_{i}"

    if len(best) >= 3:
        return best, best_src

    return [], "none"
