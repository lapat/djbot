"""
Export ~20s crossfade snippets from a rendered mix.

Each snippet = 8s of Track A clean + crossfade zone + 8s of Track B clean.
Saved as output/snippets/transition_01.mp3, transition_02.mp3, ...
"""
import os
from pydub import AudioSegment


def export_snippets(
    mix: AudioSegment,
    transitions: list[dict],
    output_dir: str = "output/snippets",
    pre_sec: float = 8.0,
    post_sec: float = 8.0,
) -> list[str]:
    """
    transitions: list of {crossfade_start_ms, crossfade_duration_ms, track_a, track_b}
    Returns list of exported file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []

    for i, t in enumerate(transitions, 1):
        start_ms  = max(0, t["crossfade_start_ms"] - int(pre_sec * 1000))
        end_ms    = min(len(mix), t["crossfade_start_ms"] + t["crossfade_duration_ms"] + int(post_sec * 1000))
        snippet   = mix[start_ms:end_ms]

        name_a = t.get("track_a", f"Track {i}")[:30]
        name_b = t.get("track_b", f"Track {i+1}")[:30]
        fname  = f"transition_{i:02d}.mp3"
        path   = os.path.join(output_dir, fname)

        snippet.export(path, format="mp3", bitrate="256k")
        dur = len(snippet) / 1000
        print(f"  [{i:02d}] {fname}  ({dur:.0f}s)  {name_a} → {name_b}")
        paths.append(path)

    return paths
