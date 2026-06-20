"""
ISLES RISING — Bicep Belfast melodic techno brain.

Style: Belfast melancholy, rave nostalgia, emotional builds. 122-126 BPM.
Artists: Bicep, Bicep & Hammer (Dahlia).
"""

STYLE_NAME    = "bicep"
BPM_RANGE     = (120, 127)
CF_BARS       = 16
OUTRO_BARS    = 60
SNIPPET_SEC   = 15
SKIP_SNIPPETS = True

SET_NAME = "isles_rising"

SET_NOTES = """\
ISLES RISING
DJ BICEPBOT

Matt and Marcus grew up crate-digging Belfast record shops. Their tracks sound \
like that — like someone who remembers the 90s rave era not with nostalgia but \
with an urgent need to rebuild it, better this time, with more bass and more \
emotional weight.

Opens with Just — melodic, patient, classic. Ayr builds the tension, then \
Meli and Orca are the heat of the set. Saku with Clara La San is the peak — \
that melody has no right to hit as hard as it does. Lido brings it home: \
warm, patient, Belfast melancholy all the way to the last bar.

122-134 BPM, 6 tracks, ~38 minutes. All transitions by DJBOT.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Bicep — Just (Original Mix)                             122 BPM  opening
  02  Bicep — Ayr                                             124 BPM  rising
  03  Bicep — Meli (II)                                       124 BPM  heat
  04  Bicep — Orca (Original Mix)                            125 BPM  intensity
  05  Bicep feat. Clara La San — Saku (Extended)             134 BPM  PEAK
  06  Bicep — Lido (Telematik Edit)                           124 BPM  closing
"""

TRACKS = [
    {
        "name":        "Just",
        "label":       "Bicep - Just (Original Mix)",
        "path":        "downloads/new_tracks/KEIr-44bCj4.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Ayr",
        "label":       "Bicep - Ayr",
        "path":        "downloads/new_tracks/1VVE9k0TzSM.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Meli",
        "label":       "Bicep - Meli (II)",
        "path":        "downloads/new_tracks/myDq5LwbxuU.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Orca",
        "label":       "Bicep - Orca (Original Mix)",
        "path":        "downloads/new_tracks/QV58Z5Xsy4o.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Saku",
        "label":       "Bicep feat. Clara La San - Saku (Extended Mix)",
        "path":        "downloads/new_tracks/eZWY0YtOAOk.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Lido",
        "label":       "Bicep - Lido (Telematik Edit)",
        "path":        "downloads/new_tracks/ZsxrCuH0Ae0.mp3",
        "hint":        126.0,
        "mix_in_bars": 32,
    },
]
