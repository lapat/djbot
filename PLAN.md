# DJBot — Auto DJ Platform Plan

## Vision
Clone a real DJ's style (starting with Chris Luno) by ingesting their YouTube mixes,
learning their patterns, and generating new mixes that sound like them.

## Research Summary (June 2025)

### What's buildable today
| Capability | Tool | Notes |
|---|---|---|
| BPM detection | `beat_this` (F1 ~89%) | pip install, GPU optional |
| Key / Camelot detection | `essentia` | Full Camelot wheel support |
| Beat-aligned time-stretch | `pyrubberband` | Gradual ramp over bars |
| Crossfade / volume ramp | `pydub`, `ffmpeg` | Render to file, not live |
| Stem split (vocals/drums/bass) | `demucs` (HTDemucs) | Offline only, ~9.2 SDR |
| Track identification | `shazamio`, `pyacoustid` | Fingerprint from audio |
| YouTube download | `yt-dlp` | MP3 extraction |

### Key constraint: pre-rendered, not live
All mixing is computed offline and saved as an audio file (MP3/WAV).
Live real-time mixing in Python is currently too degraded in quality to be useful.
This is the same as editing a movie — render first, play the finished file.

### Why ML won't clone Chris Luno (yet)
The best published ML approach (DJtransGAN, ICASSP 2022) only matched a simple
linear crossfade in blind listening tests. No system has beaten a human DJ as of 2025.
The style cloning will come from **rules extracted from his sets**, not end-to-end ML.

---

## Phases

### Phase 0 — Two-Track Mixer POC ← current
Prove we can take two songs and output one mixed file that sounds good.

**Steps:**
1. `yt-dlp` downloads Track A and Track B as MP3
2. `essentia` detects BPM + key (Camelot code) on both
3. `beat_this` finds exact beat timestamps
4. `pyrubberband` time-stretches Track B to match Track A's BPM (gradual ramp, 4 bars)
5. Find outro of A and intro of B (energy-based or fixed 32-bar rule)
6. `pydub` crossfades at the beat-aligned point
7. Output: single MP3 mix file

### Phase 1 — Ingest Chris Luno's Library
1. YouTube search for "Chris Luno" 45min+ mixes
2. `yt-dlp` downloads audio + `--write-info-json` captures comments
3. Parse comment tracklists (timestamps + track names)
4. `shazamio` / `pyacoustid` verifies/fills gaps
5. SQLite DB: `(mix_id, position, title, artist, start_time, bpm, key, camelot)`

### Phase 2 — Style Analysis
Extract from each mix:
- Transition timestamps + duration (how many bars?)
- BPM delta at each transition (same BPM? +2? -2?)
- Key compatibility (Camelot-compatible always? sometimes?)
- Energy arc across the full set (opener profile, peak, closer)
- Opener and closer track characteristics

Output: "Chris Luno style fingerprint" — a set of statistical rules

### Phase 3 — Mix Generation
Given a library of new tracks (downloaded + analyzed):
1. Pick opener matching his opener profile
2. At each step, pick next track by: compatible Camelot key, BPM in range, energy level
3. Generate each transition using his signature crossfade duration/technique
4. Apply Demucs stem-based EQ transitions (fade drum stem independently)
5. Render to single MP3

---

## Stack
```
yt-dlp              YouTube audio download
ffmpeg              audio cutting, encoding (backbone)
beat_this           beat/downbeat timestamps
essentia            BPM, key, Camelot
pyrubberband        time-stretching
demucs (HTDemucs)   stem splitting for EQ transitions
pydub               volume/crossfade curves
shazamio            track identification
sqlite3             style database (stdlib)
```

## Directory Structure
```
djbot/
  PLAN.md           this file
  requirements.txt  pip dependencies
  mixer/
    __init__.py
    download.py     yt-dlp wrapper
    analyze.py      BPM, key, beat detection
    transition.py   time-stretch + crossfade logic
    render.py       ffmpeg output
  ingest/
    scrape.py       YouTube mix finder + comment parser
    identify.py     shazamio / pyacoustid track ID
    database.py     SQLite style DB
  generate/
    selector.py     track selection by style rules
    setlist.py      full set builder
  tests/
    test_two_track.py  POC: mix two tracks
```
