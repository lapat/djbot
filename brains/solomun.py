"""
DJ SOLOMONBOT — Solomun style brain.

Style: Deep hypnotic house, 120-126 BPM, Diynamic / Innervisions / Watergate world.
      Dark, ritualistic, Ibiza — music as ceremony, not entertainment.
Influences: Âme, Adana Twins, Kollektiv Turmstrasse, Stimming, Rampa,
            Tube & Berger, Tale Of Us, Dixon, Butch, Recondite, Adriatique.
"""

STYLE_NAME   = "solomun"
BPM_RANGE    = (118, 128)
CF_BARS      = 16
OUTRO_BARS   = 90   # per-track outro_bars below override this
SNIPPET_SEC  = 15

SET_NAME = "sorry_i_am_late"

SET_NOTES = """\
SORRY I AM LATE
A DJ set by Claude for Louis Lapat  |  DJ SOLOMONBOT

The DJ arrives late. But lateness, here, is a kind of ritual — the crowd has \
already been there an hour, already broken something open inside themselves, \
already surrendered to the bass. Kollektiv Turmstrasse's Sorry I Am Late opens \
it exactly as it should: an apology that is also a seduction. Butch's Lale and \
Solomun's Somebody's Story deepen the trance — the G-minor home, the heartbeat \
of Ibiza's back rooms. The Adana Twins arrive as a pair, Everyday then Strange, \
two sides of the same ritual. Johannes Brecht's Synesthetic pulls the fog closer. \
Âme's Fiori surfaces like a memory — something you knew once and forgot and now \
feel again in your chest. Patrice Baumel's Serpent coils through the room. \
Innellea, Julian Wassermann, Nicone & Braemer, Guy Gerber & Dixon — four voices \
locked in the same G-minor prayer, the groove at maximum density. Solomun's \
Amanacer carries it to its longest breath. Tube & Berger hold the center as \
Rampa's 2000 begins the ascent. Adriatique's Ray burns at 9B — a major-key \
revelation in the middle of the night. Tale Of Us carries you to the edge of \
something nameless. Âme's Rej hits like a prayer answered. Rampa's The Touch \
is the consecration — the moment the whole room becomes one breath, one body. \
And after, only Stimming remains: Die Liebe, a single word meaning love, playing \
as the lights come up, as the island exhales, as you walk out into the impossible \
blue of Mediterranean morning. Twenty voices. One night. You don't remember it \
ending. You just run out of dark.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Kollektiv Turmstrasse — Sorry I Am Late         2B  122 BPM
  02  Butch — Lale                                    2A  124 BPM
  03  Solomun — Somebody's Story                      2A  124 BPM
  04  Adana Twins — Everyday                          4A  120 BPM
  05  Adana Twins — Strange                           ?   120 BPM
  06  Johannes Brecht — Synesthetic                   4A  120 BPM
  07  Âme — Fiori (Dixon Beat Edit)                   4A  123 BPM
  08  Patrice Baumel — Serpent                        5A  123 BPM
  09  Innellea — Forced To Bend                       6A  120 BPM
  10  Julian Wassermann — Sirius                      6A  124 BPM
  11  Nicone & Sascha Braemer — Rej Senhor            6A  123 BPM
  12  Guy Gerber & Dixon — No Distance                6A  122 BPM
  13  Solomun — Amanacer                              6A  120 BPM
  14  Tube & Berger — Imprint Of Pleasure             8A  122 BPM
  15  Rampa — 2000                                    8A  123 BPM
  16  Adriatique — Ray                                9B  123 BPM
  17  Tale Of Us & Mind Against — Astral              10A 125 BPM
  18  Âme — Rej                                       ?   125 BPM
  19  Rampa — The Touch                               6A  125 BPM  PEAK
  20  Stimming — Die Liebe                            7B  126 BPM  close

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  2B → 2A → 2A         (opening dark zone — ritual entrance)
  2A → 4A → 4A → 4A   (emotional deepening — Adana + Brecht + Fiori)
  4A → 5A → 6A         (step up into the G-minor home)
  6A × 5 tracks        (the groove at density — Ibiza 4am)
  6A → 8A → 8A         (tension rising)
  8A → 9B → 10A        (ascent toward the peak)
  10A → ? → 6A → 7B   (the prayer, the peak, the exhale)
"""

TRACKS = [
    {
        "name":        "KT_Sorry",
        "label":       "Kollektiv Turmstrasse - Sorry I Am Late",
        "path":        "downloads/solomun/fMNdGT7yAC8.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
        "outro_bars":  124,
    },
    {
        "name":        "Butch_Lale",
        "label":       "Butch - Lale",
        "path":        "downloads/solomun/qm1Q-O17QsM.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
        "outro_bars":  127,
    },
    {
        "name":        "Sol_Story",
        "label":       "Solomun - Somebody's Story",
        "path":        "downloads/solomun/dMKL9dhwTlY.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
        "outro_bars":  155,
    },
    {
        "name":        "Adana_Everyday",
        "label":       "Adana Twins - Everyday",
        "path":        "downloads/solomun/Jga4pARctdk.mp3",
        "hint":        120.0,
        "mix_in_bars": 0,   # 32 landed in a loud section — start from quiet beginning
        "outro_bars":  85,
    },
    {
        "name":        "Adana_Strange",
        "label":       "Adana Twins - Strange",
        "path":        "downloads/solomun/N3iLMny-M0o.mp3",
        "hint":        120.0,
        "mix_in_bars": 32,
        "outro_bars":  91,
    },
    {
        "name":        "Brecht",
        "label":       "Johannes Brecht - Synesthetic",
        "path":        "downloads/solomun/FeuLx0IJ9Vc.mp3",
        "hint":        120.0,
        "mix_in_bars": 0,   # 32 landed in a loud section — start from quiet beginning
        "outro_bars":  133,
    },
    {
        "name":        "Ame_Fiori",
        "label":       "Ame - Fiori (Dixon Beat Edit)",
        "path":        "downloads/solomun/JC4i4gTEAw8.mp3",
        "hint":        122.0,
        "mix_in_bars": 0,   # 32 caused trash transition — start from quiet beginning
        "outro_bars":  112,
    },
    {
        "name":        "Patrice_Serpent",
        "label":       "Patrice Baumel - Serpent",
        "path":        "downloads/solomun/DYXfmb3C5EA.mp3",
        "hint":        123.0,
        "mix_in_bars": 32,
        "outro_bars":  115,
    },
    {
        "name":        "Innellea",
        "label":       "Innellea - Forced To Bend",
        "path":        "downloads/solomun/WqL3Tko5Ui0.mp3",
        "hint":        120.0,
        "mix_in_bars": 32,
        "outro_bars":  85,
    },
    {
        "name":        "Wassermann",
        "label":       "Julian Wassermann - Sirius",
        "path":        "downloads/solomun/7_0bE2cpsP8.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
        "outro_bars":  80,
    },
    {
        "name":        "Nicone",
        "label":       "Nicone & Sascha Braemer - Rej Senhor",
        "path":        "downloads/solomun/epy0H7BholA.mp3",
        "hint":        123.0,
        "mix_in_bars": 32,
        "outro_bars":  110,
    },
    {
        "name":        "GuyGerber",
        "label":       "Guy Gerber & Dixon - No Distance",
        "path":        "downloads/solomun/yHo4jobFpD0.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
        "outro_bars":  118,
    },
    {
        "name":        "Sol_Amanacer",
        "label":       "Solomun - Amanacer",
        "path":        "downloads/solomun/sPVVe79mrXo.mp3",
        "hint":        120.0,
        "mix_in_bars": 32,
        "outro_bars":  152,
    },
    {
        "name":        "TubeNBerger",
        "label":       "Tube & Berger - Imprint Of Pleasure",
        "path":        "downloads/solomun/XQdLjaBdUuk.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
        "outro_bars":  96,
    },
    {
        "name":        "Rampa_2000",
        "label":       "Rampa - 2000",
        "path":        "downloads/solomun/2gQQL8Fszs0.mp3",
        "hint":        123.0,
        "mix_in_bars": 32,
        "outro_bars":  68,
    },
    {
        "name":        "Adriatique",
        "label":       "Adriatique - Ray",
        "path":        "downloads/solomun/jhPzoeMr5hI.mp3",
        "hint":        123.0,
        "mix_in_bars": 32,
        "outro_bars":  75,
    },
    {
        "name":        "TaleOfUs",
        "label":       "Tale Of Us & Mind Against - Astral",
        "path":        "downloads/solomun/K2eCQO-S4ws.mp3",
        "hint":        125.0,
        "mix_in_bars": 32,
        "outro_bars":  80,
    },
    {
        "name":        "Rampa_Touch",
        "label":       "Rampa - The Touch",
        "path":        "downloads/solomun/M0gFhxWkFCI.mp3",
        "hint":        125.0,
        "mix_in_bars": 8,    # TaleOfUs→Rampa_Touch known-good from prior session
        "outro_bars":  108,
    },
    {
        "name":        "Ame_Rej",
        "label":       "Ame - Rej",
        "path":        "downloads/solomun/N6uFc451SG0.mp3",
        "hint":        125.0,
        "mix_in_bars": 32,
        "outro_bars":  130,
    },
    {
        "name":        "Stimming",
        "label":       "Stimming - Die Liebe",
        "path":        "downloads/solomun/aIc3ZHiGdfQ.mp3",
        "hint":        126.0,
        "mix_in_bars": 140,   # last track: skip to last ~2.5 min
    },
]
