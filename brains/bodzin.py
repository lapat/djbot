"""
HERZBLUT MACHINE — Stephan Bodzin analog synth techno brain.

Style: Dark, hypnotic, hardware synthesizer-driven. 124-127 BPM.
Artists: Stephan Bodzin, Massano (collab tracks).
"""

STYLE_NAME    = "bodzin"
BPM_RANGE     = (122, 128)
CF_BARS       = 16
OUTRO_BARS    = 60
SNIPPET_SEC   = 15
SKIP_SNIPPETS = True

SET_NAME = "herzblut_machine"

SET_NOTES = """\
HERZBLUT MACHINE
DJ BODZINBOT

No computers touched this music. That's the Bodzin promise — every synth is \
hardware, every sequence is analog. The result is a specific kind of darkness: \
warm and relentless at the same time. You feel it in the chest before you hear \
it in the mind.

Set opens on the Massano collaborations (Healing, Falcon) — that's the entry \
point, more melodic and approachable. Strand and Zulu are the heart of the set: \
pure Bodzin, pure Herzblut, no concessions. Powers of Ten is the peak — that \
synth arpeggio has spent seven years building to this exact moment in this exact \
set. Singularity takes it over the top. Sungam and Liebe Ist bring it back down \
with a kind of resigned grace.

124-127 BPM, 8 tracks, ~50 minutes. All transitions by DJBOT.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Massano, Stephan Bodzin & Jem Cooke — Healing          126 BPM  opening
  02  Massano & Stephan Bodzin — Falcon                      126 BPM  rising
  03  Stephan Bodzin — Strand                                 126 BPM  core
  04  Stephan Bodzin — Zulu                                   124 BPM  driving
  05  Stephan Bodzin — Powers of Ten                         126 BPM  PEAK
  06  Stephan Bodzin — Singularity                            126 BPM  post-peak
  07  Stephan Bodzin — Sungam                                 124 BPM  descending
  08  Stephan Bodzin — Liebe Ist                              122 BPM  closing
"""

TRACKS = [
    {
        "name":        "Healing",
        "label":       "Massano, Stephan Bodzin & Jem Cooke - Healing",
        "path":        "downloads/new_tracks/NboVEZIHl6Q.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Falcon",
        "label":       "Massano & Stephan Bodzin - Falcon",
        "path":        "downloads/new_tracks/bTFdoMfTd4Y.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Strand",
        "label":       "Stephan Bodzin - Strand",
        "path":        "downloads/new_tracks/2x_rGWJYWAs.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Zulu",
        "label":       "Stephan Bodzin - Zulu",
        "path":        "downloads/new_tracks/T7hcAL4Cktc.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "PowersOfTen",
        "label":       "Stephan Bodzin - Powers of Ten",
        "path":        "downloads/new_tracks/8hrOW_psDlc.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Singularity",
        "label":       "Stephan Bodzin - Singularity",
        "path":        "downloads/new_tracks/AaxFuXpcQmE.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Sungam",
        "label":       "Stephan Bodzin - Sungam",
        "path":        "downloads/new_tracks/vR8lgfjCADc.mp3",
        "hint":        124.0,
        "mix_in_bars": 0,
    },
    {
        "name":        "LiebeIst",
        "label":       "Stephan Bodzin - Liebe Ist",
        "path":        "downloads/new_tracks/KNIuarCkhe8.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
]
