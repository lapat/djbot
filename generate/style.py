"""
Phase 2 — Extract Chris Luno's style fingerprint from the database.
Returns a StyleProfile used by the set builder to order and time transitions.
"""
import sqlite3
import statistics
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class StyleProfile:
    artist: str
    tracks_per_set: float          # avg number of tracks in a full set
    slot_duration_sec: float       # avg time between track starts (incl. crossfade)
    slot_stdev_sec: float          # stdev of slot durations
    crossfade_bars: int            # estimated crossfade length in bars
    top_artists: list[str]         # most-played artists in order
    signature_tracks: list[dict]   # tracks that appear 2+ times across mixes
    opener_pool: list[dict]        # tracks used to open sets


def extract(db_path: str = "djbot.db", artist_name: str = "Chris Luno") -> StyleProfile:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    artist = conn.execute(
        "SELECT id FROM artists WHERE name=?", (artist_name,)
    ).fetchone()
    if not artist:
        raise ValueError(f"Artist '{artist_name}' not found in database")

    mixes = conn.execute(
        "SELECT id, duration_sec FROM mixes WHERE artist_id=? AND tracklist_src != 'none'",
        (artist["id"],)
    ).fetchall()

    intervals = []
    for m in mixes:
        starts = [
            r["start_sec"] for r in conn.execute(
                "SELECT start_sec FROM tracks WHERE mix_id=? ORDER BY position",
                (m["id"],)
            ).fetchall()
        ]
        for i in range(1, len(starts)):
            gap = starts[i] - starts[i - 1]
            if gap > 30:   # ignore micro-gaps (duplicate/bad entries)
                intervals.append(gap)

    slot_sec  = statistics.mean(intervals) if intervals else 290
    slot_std  = statistics.stdev(intervals) if len(intervals) > 1 else 60
    n_tracks  = statistics.mean(len(conn.execute(
        "SELECT id FROM tracks WHERE mix_id=?", (m["id"],)
    ).fetchall()) for m in mixes)

    # Crossfade length: house music crossfades are typically 1–2 minutes.
    # At 4.8 min/slot and ~1.5 min crossfade → 3.3 min of unique content per track.
    # We encode this as bars: 1.5 min at 124 BPM ≈ 46 bars → round to 32 bars.
    crossfade_bars = 32

    # Most-played artists
    all_tracks = conn.execute(
        "SELECT t.title, t.artist, t.mix_id FROM tracks t "
        "JOIN mixes m ON t.mix_id=m.id WHERE m.artist_id=? AND t.title!=''",
        (artist["id"],)
    ).fetchall()
    artist_counts = Counter(t["artist"] for t in all_tracks if t["artist"])
    top_artists = [a for a, _ in artist_counts.most_common(20) if a]

    # Signature tracks (appear 2+ times)
    track_keys = [f"{t['artist']}||{t['title']}" for t in all_tracks]
    sig_counts = Counter(track_keys)
    signature_tracks = []
    for key, count in sig_counts.most_common():
        if count < 2:
            break
        artist_part, title_part = key.split("||", 1)
        signature_tracks.append({"artist": artist_part, "title": title_part, "plays": count})

    # Opener pool (position=1 tracks)
    openers = conn.execute(
        "SELECT t.title, t.artist FROM tracks t "
        "JOIN mixes m ON t.mix_id=m.id "
        "WHERE m.artist_id=? AND t.position=1 AND t.title!=''",
        (artist["id"],)
    ).fetchall()
    opener_pool = [{"artist": r["artist"], "title": r["title"]} for r in openers]

    conn.close()

    return StyleProfile(
        artist=artist_name,
        tracks_per_set=round(n_tracks, 1),
        slot_duration_sec=round(slot_sec, 1),
        slot_stdev_sec=round(slot_std, 1),
        crossfade_bars=crossfade_bars,
        top_artists=top_artists,
        signature_tracks=signature_tracks,
        opener_pool=opener_pool,
    )


def print_profile(p: StyleProfile):
    print(f"\nStyle Profile: {p.artist}")
    print(f"  Tracks/set:        {p.tracks_per_set}")
    print(f"  Slot duration:     {p.slot_duration_sec/60:.1f} min ± {p.slot_stdev_sec/60:.1f} min")
    print(f"  Crossfade:         {p.crossfade_bars} bars")
    print(f"  Top artists:       {', '.join(p.top_artists[:8])}")
    print(f"  Signature tracks:  {len(p.signature_tracks)} tracks appear 2+ times")
    for t in p.signature_tracks[:5]:
        print(f"    {t['plays']}x  {t['artist']} - {t['title']}")
    print(f"  Opener pool:       {len(p.opener_pool)} openers")
