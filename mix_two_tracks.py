#!/usr/bin/env python3
"""
DJBot Phase 0 — Two-Track Mixer POC

Downloads two tracks (or accepts local files), detects BPMs, beat-aligns them,
then crossfades Track A into Track B, saving a single mixed MP3.

Usage:
    python mix_two_tracks.py <track_a> <track_b> [options]

    track_a / track_b  YouTube URL  OR  path to a local audio file

Options:
    -o, --output       Output file path (default: output/mix.mp3)
    --crossfade-bars   Number of bars for the crossfade (default: 32)
    --outro-bars       Bars before end of A to start fading (default: 32)
    --downloads-dir    Directory for downloaded files (default: downloads/)

Examples:
    # Two YouTube URLs
    python mix_two_tracks.py "https://www.youtube.com/watch?v=AAA" \\
                             "https://www.youtube.com/watch?v=BBB"

    # Local files
    python mix_two_tracks.py track1.mp3 track2.mp3 -o my_mix.mp3

    # Mix a YouTube track into a local file
    python mix_two_tracks.py "https://youtube.com/watch?v=AAA" track2.mp3
"""
import argparse
import os
import sys

from mixer.download import download
from mixer.analyze import analyze
from mixer.transition import crossfade
from pydub import AudioSegment


def main():
    parser = argparse.ArgumentParser(
        description="Mix two tracks with a beat-aligned crossfade."
    )
    parser.add_argument("track_a", help="YouTube URL or local file for Track A (plays first)")
    parser.add_argument("track_b", help="YouTube URL or local file for Track B (fades in)")
    parser.add_argument("-o", "--output", default="output/mix.mp3", help="Output MP3 path")
    parser.add_argument("--crossfade-bars", type=int, default=32,
                        help="Number of bars for the crossfade (default: 32)")
    parser.add_argument("--outro-bars", type=int, default=32,
                        help="Bars before end of A where fade starts (default: 32)")
    parser.add_argument("--downloads-dir", default="downloads",
                        help="Directory for yt-dlp downloads (default: downloads/)")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # Step 1: Download / locate both tracks
    print("\n[1/4] Fetching tracks...")
    path_a = download(args.track_a, args.downloads_dir)
    path_b = download(args.track_b, args.downloads_dir)
    print(f"  A: {os.path.basename(path_a)}")
    print(f"  B: {os.path.basename(path_b)}")

    # Step 2: Analyze BPM + beats
    print("\n[2/4] Analyzing tracks...")
    info_a = analyze(path_a)
    info_b = analyze(path_b)

    # Step 3: Load full stereo audio for mixing
    print("\n[3/4] Loading audio for mixing...")
    seg_a = AudioSegment.from_file(path_a).set_channels(2)
    seg_b = AudioSegment.from_file(path_b).set_channels(2)
    print(f"  Track A: {len(seg_a) / 1000 / 60:.1f} min @ {info_a['bpm']:.1f} BPM")
    print(f"  Track B: {len(seg_b) / 1000 / 60:.1f} min @ {info_b['bpm']:.1f} BPM")

    # Step 4: Build the mix
    print("\n[4/4] Mixing...")
    mix, _ = crossfade(
        track_a=seg_a,
        track_b=seg_b,
        bpm_a=info_a["bpm"],
        bpm_b=info_b["bpm"],
        crossfade_bars=args.crossfade_bars,
        outro_bars=args.outro_bars,
    )

    print(f"\n  Exporting → {args.output}")
    mix.export(args.output, format="mp3", bitrate="320k")
    print(f"\nDone. Play it: open \"{args.output}\"")


if __name__ == "__main__":
    main()
