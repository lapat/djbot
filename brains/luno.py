"""
DJ LUNOBOT — Chris Luno style brain.

Style: Deep melodic house, 122-128 BPM, emotional, piano-led, Ibiza melodic.
Influences: Yotto, Stephan Bodzin, WhoMadeWho, ARTBAT, Monolink, Ben Böhmer.
"""

STYLE_NAME   = "luno"
BPM_RANGE    = (120, 128)
CF_BARS      = 8
OUTRO_BARS   = 16
SNIPPET_SEC  = 6

SET_NAME = "hours_before_light"

SET_NOTES = """\
THE HOURS BEFORE LIGHT
A DJ set by Claude for Louis Lapat  |  DJ LUNOBOT

There are hours that belong to no day — the suspended territory between 3 and 7 in the \
morning where the city exhales and the mind becomes its own mythology. This set begins \
there, with Solomun's Kreatur der Nacht, because that is what you are in those hours: \
something ancient navigating the dark by instinct. Yotto's Just Another Piano Track \
finds you at the window, the melody moving through you the way thoughts do when they're \
too large for words. Ben Böhmer's Breathing is a reminder that the body is still here, \
still asking for attention. Then Anyma and Chris Avantgarde bring the first signal back: \
Consciousness — something switches on, slow at first, a warmth behind the sternum. Jon \
Hopkins completes the awakening with Open Eye Signal, the subconscious floor cracking open, \
signals arriving from somewhere you can't name, and suddenly you know the night is ending. \
Stephan Bodzin pulls you out to the street with Boavista, the city beginning to move around \
you. WhoMadeWho and Adriatique's Miracle is the moment — the full sun of the set, the peak — \
because the miracle is simply that morning arrives again, that you made it through. ARTBAT's \
Breathe In is exactly that: the lungful of cold air outside. Horizon shows you the edge, \
the thin orange seam where night becomes something else. And Monolink's Burning Sun closes \
it without drama, the way the sun rises without asking permission, burning through whatever \
you were carrying. This is not a set about ecstasy. It is about survival and the grace that follows.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Solomun feat. Isolation Berlin — Kreatur der Nacht     11A  122 BPM  energy↗  dark
  02  Yotto — Just Another Piano Track                       10A  123 BPM  energy↑  melancholic
  03  Ben Böhmer, Nils Hoffmann & Malou — Breathing           9A  122 BPM  energy→  tender
  04  Anyma & Chris Avantgarde — Consciousness                 6A  124 BPM  energy↑↑ awakening
  05  Jon Hopkins — Open Eye Signal                            4A  122 BPM  energy↓  deep dive
  06  Stephan Bodzin — Boavista                                5A  124 BPM  energy↑  moving
  07  WhoMadeWho & Adriatique — Miracle                        5A  123 BPM  energy↑↑↑ PEAK
  08  ARTBAT — Breathe In                                      5B  127 BPM  energy↘  full breath
  09  ARTBAT — Horizon                                         4A  124 BPM  energy↗  wide open
  10  Monolink — Burning Sun                                  10A  122 BPM  energy↘  close

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  11A → 10A → 9A     (descending minor wheel — going deeper into the night)
  9A → 6A → 4A       (consciousness emerges, eye opens — 3+2 steps toward light)
  4A → 5A → 5A → 5B  (the ascent — adjacent steps climbing the wheel)
  5B → 4A → 10A      (descent into morning — closing the circle)
"""

TRACKS = [
    {
        "name":        "Kreatur",
        "label":       "Solomun - Kreatur der Nacht",
        "path":        "downloads/new_tracks/Zn28G5-6Jow.mp3",
        "hint":        122.0,
        "mix_in_bars": 8,
    },
    {
        "name":        "JustPiano",
        "label":       "Yotto - Just Another Piano Track",
        "path":        "downloads/new_tracks/MW9xQzimoV0.mp3",
        "hint":        123.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Breathing",
        "label":       "Ben Bohmer - Breathing",
        "path":        "downloads/new_tracks/CGUFF7aXjTw.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Conscious",
        "label":       "Anyma & Chris Avantgarde - Consciousness",
        "path":        "downloads/new_tracks/DYh0fLDaxm0.mp3",
        "hint":        122.0,
        "mix_in_bars": 8,
    },
    {
        "name":        "OpenEye",
        "label":       "Jon Hopkins - Open Eye Signal",
        "path":        "downloads/new_tracks/Q04ILDXe3QE.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Boavista",
        "label":       "Stephan Bodzin - Boavista",
        "path":        "downloads/new_tracks/owlsglILb1E.mp3",
        "hint":        124.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Miracle",
        "label":       "WhoMadeWho & Adriatique - Miracle",
        "path":        "downloads/new_tracks/FPA5r9GaasY.mp3",
        "hint":        123.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "BreatheIn",
        "label":       "ARTBAT - Breathe In",
        "path":        "downloads/new_tracks/1LnLTDWHiUg.mp3",
        "hint":        127.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Horizon",
        "label":       "ARTBAT - Horizon",
        "path":        "downloads/new_tracks/50zeHzEwgoI.mp3",
        "hint":        124.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "BurningSun",
        "label":       "Monolink - Burning Sun",
        "path":        "downloads/new_tracks/CRLw8p_vLls.mp3",
        "hint":        122.0,
        "mix_in_bars": 8,
    },
]
