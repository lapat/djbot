"""
PATTERN RECOGNITION — Patrice Bäumel style brain.

Style: Dark, introspective melodic techno. Precise rhythms, melodic depth, 122-126 BPM.
Patrice Bäumel's own catalog — Global Underground 42 era through current Afterlife/Kompakt output.
"""

STYLE_NAME    = "baumel"
BPM_RANGE     = (120, 127)
CF_BARS       = 16
OUTRO_BARS    = 90
SNIPPET_SEC   = 15
SKIP_SNIPPETS = True

SET_NAME = "pattern_recognition"

SET_NOTES = """\
PATTERN RECOGNITION
DJBOT — PATRICE BÄUMEL ENGINE

Patrice Bäumel occupies a very specific frequency. Not the pure darkness of Berghain, \
not the euphoria of Ibiza — something more internal, almost diagnostic. He sounds like \
a machine learning to dream. The Cave opens this set in that register: deep, structural, \
methodical. Serpent is where the floor locks in — coiling rhythm, nowhere to hide. \
Luce is the exhale, something warmer, the light that was there the whole time but you \
only notice when the beat shifts. Puppets is the question mark in the middle, the section \
where you don't know if you're the puppet or the hand. Receiver is the peak — unmistakable, \
the frequency everyone in the room finds simultaneously. The Best Part closes it because \
that's what it is: the part that stays with you after the music stops.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Patrice Bäumel — The Cave                       4A  124 BPM  energy↗  structural
  02  Patrice Bäumel — Serpent                        5A  123 BPM  energy↑  coiling
  03  Patrice Bäumel — Luce feat. Chiara Gamo         5A  122 BPM  energy→  light
  04  Patrice Bäumel — Puppets                        6A  124 BPM  energy↑  questioning
  05  Patrice Bäumel — Receiver                       7A  126 BPM  energy↑↑ PEAK
  06  gardenstate & Bien — The Best Part              5B  122 BPM  energy↘  resolution
       (Patrice Bäumel Extended Mix)

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  4A → 5A → 5A   (building in the circle, root stays)
  5A → 6A → 7A   (ascending toward peak — 2 steps)
  7A → 5B         (peak to parallel minor — emotional shift down)
"""

TRACKS = [
    {
        "name":        "TheCave",
        "label":       "Patrice Baumel - The Cave (Extended Mix)",
        "path":        "downloads/new_tracks/4pBZrnn-nW8.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Serpent",
        "label":       "Patrice Baumel - Serpent",
        "path":        "downloads/new_tracks/DYXfmb3C5EA.mp3",
        "hint":        123.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Luce",
        "label":       "Patrice Baumel - Luce feat. Chiara Gamo (Extended Mix)",
        "path":        "downloads/new_tracks/yjlbNiYriX8.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Puppets",
        "label":       "Patrice Baumel - Puppets (Extended Mix)",
        "path":        "downloads/new_tracks/HCsTJZFadok.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Receiver",
        "label":       "Patrice Baumel - Receiver",
        "path":        "downloads/new_tracks/CAwGqYA4vBs.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "BestPart",
        "label":       "gardenstate & Bien - The Best Part (Patrice Baumel Extended Mix)",
        "path":        "downloads/new_tracks/tzXQtwp-Ss8.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
]
