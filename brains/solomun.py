"""
DJ SOLOMONBOT — Solomun style brain.

Style: Deep hypnotic house, 120-126 BPM, Diynamic / Innervisions / Watergate world.
      Dark, ritualistic, Ibiza — music as ceremony, not entertainment.
Influences: Âme, Adana Twins, Kollektiv Turmstrasse, Stimming, Rampa,
            Tube & Berger, Tale Of Us, Dixon.
"""

STYLE_NAME   = "solomun"
BPM_RANGE    = (118, 128)
CF_BARS      = 8
OUTRO_BARS   = 16
SNIPPET_SEC  = 6

SET_NAME = "sorry_i_am_late"

SET_NOTES = """\
SORRY I AM LATE
A DJ set by Claude for Louis Lapat  |  DJ SOLOMONBOT

The DJ arrives late. The crowd has already been there an hour, already broken something \
open inside themselves, already surrendered to the bass. It doesn't matter. The music \
waits for no one and everyone. Kollektiv Turmstrasse's Sorry I Am Late opens it exactly \
as it should — an apology that is also a seduction, a hypnotic groove that says: I know \
you've been waiting, and that waiting was the point. The Adana Twins pull you deeper, \
into the texture of the floor, the sweat, the ritual patience of bodies that have learned \
to let go. Âme's Fiori arrives like a memory surfacing — something you knew once and forgot \
and now feel again in your chest. Tube & Berger hold the center, the rhythm that doesn't \
break. Rampa's 2000 is the first real rush — the crowd pushes forward, something shifts. \
Âme's Rej hits like a prayer answered in the fourth hour of dancing. Tale Of Us carry \
you to the edge of something nameless. And then Rampa's The Touch — the peak, the \
consecration, the moment the whole room becomes one breath. And after, only Stimming \
remains: Die Liebe, a single word meaning love, playing as the lights come up, as the \
island exhales, as you walk out into the impossible blue of Mediterranean morning. The \
music doesn't end. You just run out of night.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Kollektiv Turmstrasse — Sorry I Am Late            2B   122 BPM  energy↗  hypnotic
  02  Adana Twins — Everyday                             4A   120 BPM  energy↓  deep
  03  Adana Twins — Strange                               ?   120 BPM  energy→  ritual
  04  Âme — Fiori (Dixon Beat Edit)                     4A   123 BPM  energy↑↑ memory
  05  Tube & Berger — Imprint Of Pleasure               8A   122 BPM  energy→  grounded
  06  Rampa — 2000                                      8A   123 BPM  energy↑↑ rising
  07  Âme — Rej                                          ?   125 BPM  energy↗  prayer
  08  Tale Of Us & Mind Against — Astral                10A  125 BPM  energy↑  edge
  09  Rampa — The Touch                                  6A  125 BPM  energy↑↑↑ PEAK
  10  Stimming — Die Liebe                               7B  126 BPM  energy↓↓ exhale

── HARMONIC ARC ───────────────────────────────────────────────────────────────
  2B → 4A → 4A    (opening — adjacent steps, Adana twins share the key)
  4A → 8A → 8A    (mid-set build — 4 steps, then same key lock)
  8A → 10A → 6A   (ascent through the wheel — 2+4 steps toward peak)
  6A → 7B         (the close — adjacent, minor to relative major, the exhale)
"""

TRACKS = [
    {
        "name":        "KT_Sorry",
        "label":       "Kollektiv Turmstrasse - Sorry I Am Late",
        "path":        "downloads/solomun/fMNdGT7yAC8.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Adana_Everyday",
        "label":       "Adana Twins - Everyday",
        "path":        "downloads/solomun/Jga4pARctdk.mp3",
        "hint":        120.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Adana_Strange",
        "label":       "Adana Twins - Strange",
        "path":        "downloads/solomun/N3iLMny-M0o.mp3",
        "hint":        120.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Ame_Fiori",
        "label":       "Ame - Fiori (Dixon Beat Edit)",
        "path":        "downloads/solomun/JC4i4gTEAw8.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "TubeNBerger",
        "label":       "Tube & Berger - Imprint Of Pleasure",
        "path":        "downloads/solomun/XQdLjaBdUuk.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Rampa_2000",
        "label":       "Rampa - 2000",
        "path":        "downloads/solomun/2gQQL8Fszs0.mp3",
        "hint":        123.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Ame_Rej",
        "label":       "Ame - Rej",
        "path":        "downloads/solomun/N6uFc451SG0.mp3",
        "hint":        125.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "TaleOfUs",
        "label":       "Tale Of Us & Mind Against - Astral",
        "path":        "downloads/solomun/K2eCQO-S4ws.mp3",
        "hint":        125.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Rampa_Touch",
        "label":       "Rampa - The Touch",
        "path":        "downloads/solomun/M0gFhxWkFCI.mp3",
        "hint":        125.0,
        "mix_in_bars": 16,
    },
    {
        "name":        "Stimming",
        "label":       "Stimming - Die Liebe",
        "path":        "downloads/solomun/aIc3ZHiGdfQ.mp3",
        "hint":        126.0,
        "mix_in_bars": 8,
    },
]
