# DJ Bot — Project Rules for Claude

## Non-negotiable quality gate
**Transitions MUST be beat-matched before presenting to the user.**
- Measure phase error directly from the blend file (linear regression over all detected beats)
- Pass threshold: < 20ms phase error
- If a transition fails, fix it — do not show it to the user
- Never report a transition as done without running this check

## Crossfade settings
- Default CF_BARS = 8 (8 bars ≈ 15s at 122 BPM)
- Mix-in point: bar 16 of the incoming track (skip sparse intro)
- OUTRO_BARS = 16 (start blend 16 bars from end of outgoing track)

## Transition export format
- Export the transition moment only: ~12 seconds around the blend midpoint
- Not the full blend audio, not PRE/POST — just the crossover itself
- Full mix goes in FULL_SET.mp3 separately

## Full mix assembly
- Use stretched B audio for the body section (avoids tempo jump at blend→body boundary)
- All body sections play at the tempo they were stretched to during the blend
- Last track: play to end in stretched audio

## Output folders
- `output/final_set/`     — current canonical set (FULL_SET.mp3 + transition snippets + SET_NOTES.txt)
- `output/transitions/`   — raw per-pair build artifacts (PRE/BLEND/POST/FULL)
- `output/final_blends/`  — validated 8-bar blends
- `output/final_blends_16bar/` — validated 16-bar blends

## Beat detection
- Primary: beat_this (CPJKU, checkpoint='final0', dbn=False)
- Startup bias fix: start detection clip 2 beats BEFORE the target point (gives model audio context)
- Anchor cache: downloads/library/beatgrid_cache.json
- Phase measurement: blend-file linear regression (NOT PRE/POST file approach — that has ±30ms noise)
