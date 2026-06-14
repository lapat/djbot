#!/usr/bin/env python3
"""
Phase 3 — Generate a DJ mix in Chris Luno's style.

1. Reads his style fingerprint from the DB
2. Downloads + analyzes his most-played tracks
3. Orders them by BPM (smooth transitions)
4. Renders beat-aligned crossfades
5. Exports:
   - output/snippets/transition_XX.mp3  (20s each — what you listen to)
   - output/full_mix.mp3                (full set)
   - Cue sheet printed to stdout

Usage:
    python generate_mix.py
    python generate_mix.py --artist "Chris Luno" --tracks 10 --snippets-only
"""
import argparse
import os
from pydub import AudioSegment

from generate.style import extract, print_profile
from generate.library import build_library
from generate.snippets import export_snippets
from mixer.transition import crossfade


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist", default="Chris Luno")
    parser.add_argument("--tracks", type=int, default=8, help="Number of tracks to mix")
    parser.add_argument("--crossfade-bars", type=int, default=32)
    parser.add_argument("--outro-bars", type=int, default=32)
    parser.add_argument("--snippets-only", action="store_true",
                        help="Skip rendering full mix, only export snippets")
    parser.add_argument("--db", default="djbot.db")
    args = parser.parse_args()

    os.makedirs("output/snippets", exist_ok=True)

    # ── Phase 2: style fingerprint ─────────────────────────────────────────
    print(f"\n[1] Reading {args.artist}'s style from database...")
    profile = extract(args.db, args.artist)
    print_profile(profile)

    # ── Build track list: signature tracks first, then variety ────────────
    # Use his signature tracks (most-played) as candidates
    candidates = [
        {"artist": t["artist"], "title": t["title"]}
        for t in profile.signature_tracks
    ]
    # Pad with opener pool if needed
    for o in profile.opener_pool:
        if len(candidates) >= args.tracks * 3:
            break
        if o not in candidates:
            candidates.append(o)

    # ── Phase 2 → 3: download & analyze ───────────────────────────────────
    print(f"\n[2] Building track library ({args.tracks} tracks target)...")
    library = build_library(candidates, max_tracks=args.tracks)

    if len(library) < 2:
        print("ERROR: need at least 2 tracks to make a mix. Check your internet connection.")
        return

    print(f"\n  Library ready: {len(library)} tracks")
    print(f"  {'BPM':>5}  {'Duration':>8}  Track")
    for t in library:
        print(f"  {t['bpm']:5.1f}  {t['duration_sec']/60:7.1f}m  {t['artist']} - {t['title']}")

    # ── Phase 3: render the mix ────────────────────────────────────────────
    print(f"\n[3] Rendering mix ({len(library)} tracks, {args.crossfade_bars}-bar crossfades)...")

    mix         = AudioSegment.empty()
    transitions = []
    current_ms  = 0

    for i, track in enumerate(library):
        seg = AudioSegment.from_file(track["path"]).set_channels(2)

        if i == 0:
            # First track: add clean, then plan crossfade for next
            mix = seg
            current_ms = len(seg)
            print(f"  [{i+1:02d}] {track['artist']} - {track['title']}  ({track['bpm']} BPM)")
        else:
            prev = library[i - 1]
            print(f"  [{i+1:02d}] {track['artist']} - {track['title']}  ({track['bpm']} BPM)")

            # Build the blended tail: last N bars of current mix + new track
            seconds_per_bar   = (60.0 / prev["bpm"]) * 4
            crossfade_ms_est  = int(seconds_per_bar * args.crossfade_bars * 1000)
            outro_ms          = int(seconds_per_bar * args.outro_bars * 1000)
            crossfade_start   = max(0, len(mix) - outro_ms)

            # Record where this transition lands before we lengthen the mix
            transitions.append({
                "crossfade_start_ms":    crossfade_start,
                "crossfade_duration_ms": crossfade_ms_est,
                "track_a": f"{prev['artist']} - {prev['title']}",
                "track_b": f"{track['artist']} - {track['title']}",
                "bpm_a":   prev["bpm"],
                "bpm_b":   track["bpm"],
            })

            # Render the actual crossfade
            # Keep everything before the outro, then blend
            prev_seg  = mix            # full mix so far
            next_seg  = seg

            mix = crossfade(
                track_a=prev_seg,
                track_b=next_seg,
                bpm_a=prev["bpm"],
                bpm_b=track["bpm"],
                crossfade_bars=args.crossfade_bars,
                outro_bars=args.outro_bars,
            )

    # ── Cue sheet ──────────────────────────────────────────────────────────
    print(f"\n{'━'*60}")
    print(f"  CUE SHEET — {args.artist} bot mix")
    print(f"{'━'*60}")
    # Reconstruct track start times from transition data
    starts = []
    pos_ms = 0
    for i, track in enumerate(library):
        if i == 0:
            starts.append(0)
        else:
            t = transitions[i - 1]
            starts.append(t["crossfade_start_ms"])
    for i, (track, start) in enumerate(zip(library, starts), 1):
        m, s = divmod(start // 1000, 60)
        marker = " ← crossfade" if i > 1 else " ← opener"
        print(f"  {i:2d}. {m:02d}:{s:02d}  {track['artist']} - {track['title']}{marker}")

    total_min = len(mix) / 1000 / 60
    print(f"{'━'*60}")
    print(f"  Total: {total_min:.1f} min\n")

    # ── Export snippets ────────────────────────────────────────────────────
    print(f"[4] Exporting transition snippets → output/snippets/")
    export_snippets(mix, transitions, output_dir="output/snippets")

    # ── Export full mix (unless --snippets-only) ───────────────────────────
    if not args.snippets_only:
        full_path = "output/full_mix.mp3"
        print(f"\n[5] Exporting full mix → {full_path}")
        mix.export(full_path, format="mp3", bitrate="320k")
        print(f"  Done. {total_min:.1f} min, {os.path.getsize(full_path)//1024//1024} MB")

    print(f"\nSnippets: open output/snippets/")
    if not args.snippets_only:
        print(f"Full mix: open output/full_mix.mp3")


if __name__ == "__main__":
    main()
