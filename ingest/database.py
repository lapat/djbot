"""SQLite database for DJ library ingestion."""
import sqlite3
import os
from contextlib import contextmanager

DEFAULT_DB = "djbot.db"


def init_db(path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS artists (
            id          INTEGER PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS mixes (
            id              INTEGER PRIMARY KEY,
            artist_id       INTEGER REFERENCES artists(id),
            youtube_id      TEXT UNIQUE NOT NULL,
            title           TEXT,
            duration_sec    INTEGER,
            url             TEXT,
            audio_path      TEXT,
            tracklist_raw   TEXT,
            tracklist_src   TEXT,  -- 'description' | 'comment' | 'none'
            ingested_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id              INTEGER PRIMARY KEY,
            mix_id          INTEGER REFERENCES mixes(id),
            position        INTEGER,
            title           TEXT,
            artist          TEXT,
            start_sec       REAL,
            end_sec         REAL,
            bpm             REAL,
            key_name        TEXT,
            camelot         TEXT,
            identified      INTEGER DEFAULT 0,
            UNIQUE(mix_id, position)
        );
    """)
    conn.commit()
    return conn


@contextmanager
def get_db(path: str = DEFAULT_DB):
    conn = init_db(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_artist(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM artists WHERE name=?", (name,)).fetchone()["id"]


def upsert_mix(conn: sqlite3.Connection, artist_id: int, data: dict) -> int:
    conn.execute("""
        INSERT INTO mixes (artist_id, youtube_id, title, duration_sec, url)
        VALUES (:artist_id, :youtube_id, :title, :duration_sec, :url)
        ON CONFLICT(youtube_id) DO UPDATE SET
            title        = excluded.title,
            duration_sec = excluded.duration_sec
    """, {**data, "artist_id": artist_id})
    return conn.execute(
        "SELECT id FROM mixes WHERE youtube_id=?", (data["youtube_id"],)
    ).fetchone()["id"]


def save_tracklist(conn: sqlite3.Connection, mix_id: int, tracks: list[dict], source: str):
    conn.execute(
        "UPDATE mixes SET tracklist_src=? WHERE id=?", (source, mix_id)
    )
    for i, t in enumerate(tracks):
        conn.execute("""
            INSERT INTO tracks (mix_id, position, title, artist, start_sec, end_sec)
            VALUES (:mix_id, :position, :title, :artist, :start_sec, :end_sec)
            ON CONFLICT(mix_id, position) DO UPDATE SET
                title    = excluded.title,
                artist   = excluded.artist,
                start_sec= excluded.start_sec,
                end_sec  = excluded.end_sec
        """, {
            "mix_id": mix_id,
            "position": i + 1,
            "title": t.get("title", ""),
            "artist": t.get("artist", ""),
            "start_sec": t.get("start_sec", 0.0),
            "end_sec": t.get("end_sec"),
        })
