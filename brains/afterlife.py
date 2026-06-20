"""
PALE TRANSMISSIONS — Afterlife-label melodic techno brain.

Style: Dark, cosmic, emotional melodic techno. 122-126 BPM.
Influences: Massano, Agents of Time, Kevin de Vries, ARTBAT, Innellea,
            Patrice Bäumel, Adriatique, Yotto, Monolink.
"""

STYLE_NAME    = "afterlife"
BPM_RANGE     = (120, 127)
CF_BARS       = 16
OUTRO_BARS    = 60
SNIPPET_SEC   = 15
SKIP_SNIPPETS = True

SET_NAME = "pale_transmissions"

SET_NOTES = """\
PALE TRANSMISSIONS
DJBOT — AFTERLIFE ENGINE

Been deep in the Afterlife catalog lately — Massano, Innellea, Agents of Time, ARTBAT, \
Patrice Bäumel. These records take their time, and the build actually pays off.

Sequence starts with Innellea's Golden Fort to set the tone: dark, structural, melodic. \
Moves through Adriatique, Yotto, and Monolink in the early stretch — BPM locked at 122 \
but the mood shifts track by track. Agents of Time pushes it into more driving territory \
at the midpoint. ARTBAT and Kevin de Vries take it up further from there. Patrice Bäumel's \
Receiver is the peak. Lane 8 and Massano bring it back down, and Thodoris Triantafillou \
closes it out.

37 minutes. All transitions mixed by DJBOT — no human touched the cue points.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Innellea — The Golden Fort                              4A   122 BPM  energy↗  deep/structural
  02  Adriatique & Emmit Fenn — Closer                       ?A   122 BPM  energy→  atmospheric
  03  Yotto — Radiate                                        2A   122 BPM  energy↑  melodic
  04  Monolink — Father Ocean                               10A   122 BPM  energy→  hypnotic
  05  Agents of Time — The Mirage                            1A   124 BPM  energy↑  driving
  06  Innellea — Distorted Youth                             ?A   122 BPM  energy↑  darker
  07  ARTBAT & Fred Lenix — Dreamcatcher                     ?A   124 BPM  energy↑↑ builds
  08  Kevin de Vries & Lehar — Tokyo Nights                  8A   124 BPM  energy↑↑↑ climbing
  09  Patrice Bäumel — Receiver                              7A   126 BPM  energy↑↑↑↑ PEAK
  10  Lane 8 feat. POLIÇA — Brightest Lights                5B   122 BPM  energy↘  embrace
  11  Massano — The Feeling                                  ?A   124 BPM  energy↘↘ cooling
  12  Thodoris Triantafillou — The Sun the Stars            11A   124 BPM  energy↘↘↘ close

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  4A → 2A → 10A    (descending minor wheel — going deeper)
  10A → 1A         (5-step jump — energy surge)
  7A → 8A          (adjacent at peak — tightest lock)
  7A → 5B          (peak to Lane 8 — parallel shift, cooling)
  11A              (final transmission — 11A closes the arc)
"""

TRACKS = [
    {
        "name":        "GoldenFort",
        "label":       "Innellea - The Golden Fort",
        "path":        "downloads/new_tracks/rGqO6JN2Nok.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Closer",
        "label":       "Adriatique & Emmit Fenn - Closer",
        "path":        "downloads/new_tracks/86FjrrwI0c4.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Radiate",
        "label":       "Yotto - Radiate",
        "path":        "downloads/new_tracks/KJ4VFdgrN-A.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "FatherOcean",
        "label":       "Monolink - Father Ocean",
        "path":        "downloads/new_tracks/pJ4m0-nsAuE.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "TheMirage",
        "label":       "Agents of Time - The Mirage",
        "path":        "downloads/new_tracks/stg7JxkNhkk.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "DistYouth",
        "label":       "Innellea - Distorted Youth",
        "path":        "downloads/new_tracks/xcdMUIG5ZVc.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Dreamcatch",
        "label":       "ARTBAT & Fred Lenix - Dreamcatcher",
        "path":        "downloads/new_tracks/iwEHbXccofE.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "TokyoNight",
        "label":       "Kevin de Vries & Lehar - Tokyo Nights",
        "path":        "downloads/new_tracks/lQVPiAhEfus.mp3",
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
        "name":        "Brightest",
        "label":       "Lane 8 feat. POLICA - Brightest Lights",
        "path":        "downloads/new_tracks/CARHyGAsv6Y.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "TheFeeling",
        "label":       "Massano - The Feeling",
        "path":        "downloads/new_tracks/Eb5Of4m5-RI.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "SunStars",
        "label":       "Thodoris Triantafillou - The Sun the Stars",
        "path":        "downloads/new_tracks/hF0V12TNE78.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
]
