#!/usr/bin/env python3
"""
Phase 1 — Ingest a DJ's YouTube library.

1. Search YouTube for long mixes by artist name
2. Fetch metadata (description + comments) for each
3. Parse tracklists from descriptions/comments
4. Store everything in djbot.db

Usage:
    python ingest_artist.py "Chris Luno"
    python ingest_artist.py "Chris Luno" --limit 5
    python ingest_artist.py "Chris Luno" --show-db
"""
import argparse
import sys

from ingest.scrape import search_mixes, fetch_metadata
from ingest.tracklist import best_tracklist
from ingest.database import get_db, upsert_artist, upsert_mix, save_tracklist


def ingest(artist_name: str, limit: int = 999, db_path: str = "djbot.db"):
    with get_db(db_path) as conn:
        artist_id = upsert_artist(conn, artist_name)
        print(f"Artist: {artist_name} (id={artist_id})")

        mixes = search_mixes(artist_name, min_duration_sec=2400, max_results=30)
        if limit:
            mixes = mixes[:limit]

        print(f"\nProcessing {len(mixes)} mixes...\n")

        total_tracks = 0
        for i, mix in enumerate(mixes, 1):
            dur_min = mix["duration_sec"] // 60
            print(f"[{i}/{len(mixes)}] {mix['title'][:60]} ({dur_min} min)")

            mix_id = upsert_mix(conn, artist_id, mix)

            # Fetch description + comments
            meta = fetch_metadata(mix["youtube_id"])
            desc_preview = (meta["description"] or "")[:80].replace("\n", " ")
            print(f"         desc: {desc_preview!r}")
            print(f"         comments fetched: {len(meta['comments'])}")

            # Parse tracklist
            tracks, source = best_tracklist(meta["description"], meta["comments"])
            print(f"         tracklist source: {source} → {len(tracks)} tracks")

            if tracks:
                save_tracklist(conn, mix_id, tracks, source)
                total_tracks += len(tracks)
                for t in tracks[:3]:
                    mins = int(t["start_sec"]) // 60
                    secs = int(t["start_sec"]) % 60
                    label = f"{t['artist']} - {t['title']}" if t["artist"] else t["title"]
                    print(f"           {mins:02d}:{secs:02d}  {label[:60]}")
                if len(tracks) > 3:
                    print(f"           ... +{len(tracks)-3} more")
            else:
                save_tracklist(conn, mix_id, [], "none")
                print(f"         [no tracklist found]")

            conn.commit()
            print()

        print(f"Done. {len(mixes)} mixes, {total_tracks} tracks total → {db_path}")


def show_db(db_path: str = "djbot.db"):
    from ingest.database import init_db
    conn = init_db(db_path)
    artists = conn.execute("SELECT * FROM artists").fetchall()
    for a in artists:
        mixes = conn.execute(
            "SELECT * FROM mixes WHERE artist_id=? ORDER BY id", (a["id"],)
        ).fetchall()
        print(f"\n{a['name']} — {len(mixes)} mixes")
        for m in mixes:
            track_count = conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE mix_id=?", (m["id"],)
            ).fetchone()[0]
            src = m["tracklist_src"] or "none"
            print(f"  {m['duration_sec']//60:3d}min  [{track_count:2d} tracks, {src}]  {m['title'][:55]}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artist", nargs="?", default="Chris Luno")
    parser.add_argument("--limit", type=int, default=999, help="Max mixes to process")
    parser.add_argument("--show-db", action="store_true", help="Print DB contents and exit")
    parser.add_argument("--db", default="djbot.db")
    args = parser.parse_args()

    if args.show_db:
        show_db(args.db)
    else:
        ingest(args.artist, limit=args.limit, db_path=args.db)
