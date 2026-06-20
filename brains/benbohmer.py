"""
BEYOND HORIZONS — Ben Böhmer melodic house/techno brain.

Style: Emotional melodic techno, Berlin warehouse meets cosmic synthesizer. 122-125 BPM.
Artists: Ben Böhmer, Ben Böhmer & Monolink, Stephan Bodzin (Böhmer remix),
         Jan Blomqvist (Böhmer remix).
"""

STYLE_NAME    = "benbohmer"
BPM_RANGE     = (120, 126)
CF_BARS       = 16
OUTRO_BARS    = 60
SNIPPET_SEC   = 15
SKIP_SNIPPETS = True

SET_NAME = "beyond_horizons"

SET_NOTES = """\
BEYOND HORIZONS
DJ BENBOT

Ben Böhmer makes music that sounds like it's arriving from somewhere far away. \
Not cosmic exactly — more like the feeling of driving home at 4am after the \
party's over and realizing the night was actually important.

Ground Control is the entry: steady, orienting. Breathing with Nils Hoffmann \
and Malou layers in the first melody — still patient. Cappadocia is where the \
set finds its emotional register, spare and wide. Purple Line is the pivot: \
eight minutes of building melodic pressure. The collaboration with Monolink on \
Black Hole brings the bass into the foreground. The Bodzin remix (LLL) and Jan \
Blomqvist remix close it out — Böhmer as interpreter, which turns out to be \
just as revealing as Böhmer as composer.

122-125 BPM, 7 tracks, ~45 minutes. All transitions by DJBOT.

── TRACKLIST ──────────────────────────────────────────────────────────────────
  01  Ben Böhmer — Ground Control                            122 BPM  opening
  02  Ben Böhmer, Nils Hoffmann & Malou — Breathing          122 BPM  melodic entry
  03  Ben Böhmer — Cappadocia                                122 BPM  emotional register
  04  Ben Böhmer — Purple Line                               124 BPM  PEAK build
  05  Ben Böhmer & Monolink — Black Hole                     124 BPM  peak
  06  Stephan Bodzin — LLL (Ben Böhmer Remix)               124 BPM  post-peak
  07  Jan Blomqvist — Space In Between (Ben Böhmer Remix)    124 BPM  closing
"""

TRACKS = [
    {
        "name":        "GroundControl",
        "label":       "Ben Bohmer - Ground Control",
        "path":        "downloads/new_tracks/9E2pX27Exkc.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Breathing",
        "label":       "Ben Bohmer, Nils Hoffmann & Malou - Breathing",
        "path":        "downloads/new_tracks/xF5PzY4b3eQ.mp3",
        "hint":        122.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "Cappadocia",
        "label":       "Ben Bohmer - Cappadocia",
        "path":        "downloads/new_tracks/upm7qgomnp0.mp3",
        "hint":        122.0,
        "mix_in_bars": 0,
    },
    {
        "name":        "PurpleLine",
        "label":       "Ben Bohmer - Purple Line",
        "path":        "downloads/new_tracks/_jWp5RpEjt0.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "BlackHole",
        "label":       "Ben Bohmer & Monolink - Black Hole",
        "path":        "downloads/new_tracks/W84W0YGxJK4.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "LLL_Remix",
        "label":       "Stephan Bodzin - LLL (Ben Bohmer Remix)",
        "path":        "downloads/new_tracks/WGIbLbLcNns.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
    {
        "name":        "SpaceInBetween",
        "label":       "Jan Blomqvist - Space In Between (Ben Bohmer Remix)",
        "path":        "downloads/new_tracks/ums8n8tTL6M.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
    },
]
