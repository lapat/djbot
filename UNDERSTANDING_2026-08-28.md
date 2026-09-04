# djbot ("DJ Kyoko") — comprehensive understanding (2026-08-28)

Read-only investigation. Written alongside `SCOPING_2026-08-28.md` (which
scoped two specific mixing upgrades) — this doc covers the whole project.

## Architecture overview

This is actually **two combined systems**, both real and both mature:

**1. The DJ mix engine** — turns a curated tracklist ("brain," one file per
DJ/artist persona under `brains/`: `afterlife.py`, `baumel.py`, `bicep.py`,
`bodzin.py`, `solomun.py`, `taleous.py`, etc.) into a beat-matched,
phase-aligned, hour-long mix:
- `mixer/download.py` — pulls source audio via yt-dlp
- `mixer/beatgrid.py` — beat detection (`beat_this`, CPJKU model, CPU
  inference), cached to `downloads/library/beatgrid_cache.json`
- `mixer/set_builder.py` (the core, ~1200+ lines) — everything documented at
  length in CLAUDE.md is real code here, confirmed present:
  `_band_split`/`_eq_blend` (v2 Pioneer-DJM-800-style per-band crossfade),
  `_bpm_ramp` (32-chunk gradual BPM nudge over the last 8 bars before a
  blend), `_phase_error_ms` (linear-regression phase measurement),
  `_octave_match` (fixes double/half-time BPM detection errors),
  `_build_hard_cut_transition`/`_echo_out_tail` (the deliberate fallback when
  beatmatching can't be trusted), `build_full_set` (top-level assembly).
- `mixer/stems.py` — Demucs stem separation, built but explicitly NOT used in
  the main blend path (documented finding: stretching stems independently
  breaks phase coherence — kept for future experiments only).
- `mixer/transition.py`, `mixer/curate.py`, `mixer/tagger.py`,
  `mixer/evaluate.py`, `mixer/voice.py` — transition helpers, track curation,
  ID3/cover-art tagging, quality evaluation, and voice-over ducking
  (`_duck_and_overlay_voice` — the mix can carry a spoken voice track).
- Non-negotiable quality gate on every transition: phase error < 20ms AND RMS
  continuity < 3.0x, enforced before any transition is shown to Louis.

**2. An AI short-film production pipeline** — separate from the mix engine,
sharing only the finished mixes as soundtrack:
- `story_pipeline/` — Gemini-chat-based character-consistent scene
  generation (FLUX 1.1 Pro stills + Gemini 3.1 Flash Image chat for identity
  continuity + Hailuo-02 first/last-frame chaining for animation), producing
  wordless short films starring Louis himself (`lou photos/` are the
  hardcoded character reference images — never synthetic).
- Extremely researched craft rules baked into CLAUDE.md: Kuleshov-effect
  cinematography (peer-reviewed fMRI grounding), a 12-scene face/environment
  ratio template, prop-selection rules ("history not function"), and a
  literature review of 2025-2026 AI film festival winners informing what
  actually lands emotionally.
- Output gets combined with a DJ mix as the soundtrack and streamed to Twitch
  (`THE_PASSAGE_*.mp4` + `full_mix.mp3`) — the two systems are genuinely one
  product, not two side projects.

**3. Distribution/orchestration layer:**
- `webapp/server.py` (660 lines) + `webapp/job_runner.py` (785 lines) — a
  real FastAPI web app that runs mix-generation jobs, referenced by
  `mac_app/` and `windows_app/` distributables literally packaged and sent to
  a friend (`For Friend — DJ Kyoko 2026-08-17/DJ Kyoko.zip`, and a Windows
  build the next day) — this has real external users beyond Louis.
- `pipeline/worker.py` (340 lines) + `quality_gate.py` + `style_selector.py`
  — a Railway-deployed automation pipeline that was running mix generation
  on a **weekly cron job** — per git log, this was explicitly disabled
  (`81faa4b Disable the weekly Railway cron job`), so the automated schedule
  is currently OFF even though the code for it still exists.
- `djbot-gallery/` (sibling project folder, Flask `app.py` + `railway.toml`)
  is the "shared gallery" mentioned in the git log — a separate small web app
  for browsing finished mixes, not part of djbot's own repo.
- Twitch live streaming and Pollinations AI cover-art generation were added
  (`0e3de9e`), and SMS notifications via Twilio when a mix/render finishes
  (`7e11f3b`).

## What's genuinely working today vs. flagged WIP

**Confirmed working, with real evidence:**
- Every function `CLAUDE.md` documents in `set_builder.py` actually exists in
  the code (`_band_split`, `_eq_blend`, `_bpm_ramp`, `_phase_error_ms`,
  `_octave_match`, `_build_hard_cut_transition`, `build_full_set`, etc.) —
  the docs are not aspirational, they match reality.
- Real, named, finished mixes exist in git/deploy history: "sorry_i_am_late"
  (63:22, 19 transitions all passing phase/RMS gates, uploaded to YouTube),
  multiple "brains" per named DJ style.
- A real security fix in the recent git log (`6aeaf48 Fix AppleScript
  injection in the iMessage/email share endpoints`) — this app handles
  untrusted input somewhere in its sharing feature; worth knowing this class
  of bug existed and was fixed, not theoretical.
- `test_set_quality.py` has real unit + integration tests (10 for
  `_bpm_ramp`, 7 for `_band_split`/`_eq_blend`, 8 for a 3-track build, 12 for
  the full 19-transition solomun set) — this isn't untested code.

**Flagged WIP / known-limited / currently off:**
- The weekly automated Railway cron pipeline is disabled — mix generation is
  not currently running on autopilot, someone has to trigger it.
- `mixer/stems.py` (Demucs) is built but deliberately unused in the main
  path — a real, documented dead end (stem-independent stretching breaks
  phase coherence), kept only for future experimentation.
- YouTube thumbnail upload was returning 403 as of the last session note
  (channel needs verification) — a known, unresolved small blocker.
- `pipeline/video_builder.py` is explicitly marked "legacy... abandoned, kept
  for reference" in CLAUDE.md — don't treat it as the current video path.
- `output/` in the repo itself only contains test-concurrency artifacts, not
  the big finished mixes — those live wherever Railway's volume/deploy
  target actually stores them, not in git.

## Key files map

| File | Owns |
|---|---|
| `mixer/set_builder.py` | Core mix assembly, all transition math, quality gates |
| `mixer/beatgrid.py` | Beat detection + caching |
| `mixer/stems.py` | Demucs stem separation (unused in main path) |
| `brains/*.py` | Per-DJ-persona tracklists and style config |
| `pipeline/worker.py`, `quality_gate.py`, `style_selector.py` | Railway automation (currently not on a schedule) |
| `webapp/server.py`, `webapp/job_runner.py` | The FastAPI app behind the Mac/Windows distributables |
| `story_pipeline/` | AI short-film scene generation + Gemini/Hailuo-02 chaining |
| `mac_app/`, `windows_app/` | Packaged, actually-distributed friend-facing apps |
| `SCOPING_2026-08-28.md` | Sibling doc — the two proposed mixing upgrades scoped against this same code |

## Surprising findings not already in CLAUDE.md or the SCOPING doc

1. **"DJ Kyoko" is the product's real name**, distributed to at least one
   real friend on both Mac and Windows — this is not an internal-only tool,
   and the branding ties directly to Kyoko/digitaltwin's naming (the
   `djkyoko` HuggingFace/GitHub handle referenced in `digital-twin-template`
   is the same "djkyoko" identity, confirming Louis has been building a
   consistent "Kyoko" brand across at least two separate projects).
2. **The automated weekly pipeline is currently off**, not just theoretically
   available — anyone assuming djbot is producing mixes on a schedule right
   now would be wrong; it requires manual triggering since the cron was
   disabled.
3. **A real security vulnerability (AppleScript injection) was found and
   fixed** in the iMessage/email share endpoints — worth knowing this attack
   surface exists in the webapp at all, since it implies user-controlled
   input reaches an AppleScript call somewhere in the sharing flow.
4. **The story-film side is not a side project** — it's a full, independently
   research-heavy production system (peer-reviewed cinematography research,
   festival-winner analysis, character-consistency benchmarking across 30+
   sources) that happens to live in the same repo as the DJ engine because
   the finished films use djbot's mixes as soundtrack.
