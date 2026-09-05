"""
3-track proof-of-concept — KT Sorry → Butch Lale → Solomun Story

This is the reference/E2E brain used by tests/test_e2e_public.py. It expects
the 3 tracks below already downloaded to downloads/test3/<video_id>.mp3 —
the test (and scripts/download_tracks.sh-style helper it runs first) fetches
them with yt-dlp on a fresh clone, so this brain works for anyone, not just
this machine's existing local cache.
"""

STYLE_NAME   = "test"
BPM_RANGE    = (120, 126)
CF_BARS      = 16
OUTRO_BARS   = 90
SNIPPET_SEC  = 5   # 5s padding each side of blend boundary

SET_NAME  = "test_3track"
SET_NOTES = "3-track transition test"

# video_id kept alongside path so the downloader (see tests/test_e2e_public.py)
# knows exactly what to fetch without parsing the path.
TRACKS = [
    {
        "name":        "KT_Sorry",
        "label":       "Kollektiv Turmstrasse - Sorry I Am Late",
        "video_id":    "fMNdGT7yAC8",
        "path":        "downloads/test3/fMNdGT7yAC8.mp3",
        "hint":        122.0,
        "mix_in_bars": 16,
        "outro_bars":  124,   # ~4:06 body then blend
    },
    {
        "name":        "Butch_Lale",
        "label":       "Butch - Lale",
        "video_id":    "qm1Q-O17QsM",
        "path":        "downloads/test3/qm1Q-O17QsM.mp3",
        "hint":        124.0,
        "mix_in_bars": 32,
        "outro_bars":  127,   # ~2:35 body then blend
    },
    {
        "name":        "Sol_Story",
        "label":       "Solomun - Somebody's Story",
        "video_id":    "dMKL9dhwTlY",
        "path":        "downloads/test3/dMKL9dhwTlY.mp3",
        "hint":        124.0,
        "mix_in_bars": 207,   # skip to last ~2 min (last track plays to end)
    },
]
