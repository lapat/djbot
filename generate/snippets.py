"""
Export crossfade snippets for quick QA:
  3s of A clean → crossfade blend → 3s of B clean (no fading on B)
"""
import os
from pydub import AudioSegment

PRE_MS  = 3000   # ms of clean A before the blend starts
POST_MS = 3000   # ms of clean B after the blend ends


def export_snippets(
    mix: AudioSegment,
    transitions: list[dict],
    output_dir: str = "output/snippets",
) -> list[str]:
    """
    transitions: list of {crossfade_start_ms, crossfade_duration_ms, track_a, track_b}
    Each snippet: 3s of A clean → full crossfade blend → 3s of B clean.
    """
    os.makedirs(output_dir, exist_ok=True)

    paths = []
    for i, t in enumerate(transitions, 1):
        cf_start = t["crossfade_start_ms"]
        cf_dur   = t["crossfade_duration_ms"]

        start_ms = max(0, cf_start - PRE_MS)
        end_ms   = min(len(mix), cf_start + cf_dur + POST_MS)
        snippet  = mix[start_ms:end_ms]

        name_a = t.get("track_a", f"Track {i}")[:35]
        name_b = t.get("track_b", f"Track {i+1}")[:35]
        fname  = f"transition_{i:02d}.mp3"
        path   = os.path.join(output_dir, fname)

        snippet.export(path, format="mp3", bitrate="256k")
        dur = len(snippet) / 1000
        print(f"  [{i:02d}] {fname}  ({dur:.0f}s)  '{name_a}' → '{name_b}'")
        paths.append(path)

    return paths
