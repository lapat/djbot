# djbot — new features plan (2026-09-04)

Researched against the current AI-DJ and AI-short-film tool landscape, plus
real gaps found live in this session. Ordered safest/highest-value first —
this is the backlog for a 1-hour, 5-minute-cadence build loop. Every item is
scoped to be small enough to implement + test in one ~5-minute pass, and
nothing touches `mixer/set_builder.py`'s core blend math again without a
strong reason (that code just had real surgery today — treat it as fragile).

## What the market is actually doing (2026 research)

- **DJ.Studio's flagship differentiator**: AI orders a whole set by key
  compatibility + energy flow + tempo progression, not just BPM. djbot
  already built the key-detection half of this (`mixer/harmonic.py`,
  2026-08-28) but it's wired to a diagnostic report only
  (`harmonic_report.py`) — never actually used to order anything. This is
  the single highest-leverage unused asset in the codebase.
- **Pacemaker / consumer AI-DJ apps**: free, fast, mobile-first automatic
  mixing is the baseline expectation now, not a differentiator on its own —
  djbot's real edge is the beat-matching *correctness* discipline (phase
  gates, RMS gates, honest hard-cut fallback) most consumer tools don't
  have and don't disclose.
- **AI short film (2026)**: the industry converged on the same thing
  djbot's CLAUDE.md already enforces — character/prop/location consistency
  via multi-reference conditioning, wordless emotional beats carried by
  music. djbot's approach is already at the state of the art here; the gap
  is tooling (reusable character banks) not technique.

Sources:
- [DJ.Studio — AI Mixing Apps](https://dj.studio/blog/ai-mixing-apps)
- [ZIPDJ — Best AI DJ Tools 2026](https://www.zipdj.com/blog/best-ai-dj-tools)
- [DJing.ai — What Comes After Sync?](https://djing.ai/future-mixing-algorithms/)
- [PulseDJ — DJ Auto Mixer](https://blog.pulsedj.com/dj-auto-mixer)
- [AI Workflows — Best AI Tools for Short Drama 2026](https://aiworkflows.tools/blog/best-ai-tools-for-short-drama-2026)
- [Digen — Best AI Video Tools for Storytelling 2026](https://resource.digen.ai/best-ai-video-tools-for-storytelling/)

## Backlog (in build order)

1. **Harden yt-dlp downloads against concurrent-Chrome-cookie contention.**
   Root cause confirmed live today: two `--cookies-from-browser chrome`
   processes running at once (this session's batch + the installed app)
   caused two real 180s timeouts. Fix: retry once on timeout with a longer
   window before giving up, same spirit as the existing "retry bot-detection
   errors once" rule in CLAUDE.md's git history.
2. **Wire harmonic compatibility into `make_mix.py`'s curated tracklist
   ordering.** After `curate_and_validate` returns tracks, re-order them
   (subject to the existing energy-arc intent in the curation prompt) to
   prefer Camelot-adjacent neighbors where BPM is already close — a soft
   re-sort, not a hard filter, matching the philosophy already documented
   in SCOPING_2026-08-28.md. This turns the unused harmonic.py into a real
   feature.
3. **Gallery image cache-busting.** Root cause confirmed live today: a
   browser can cache a failed image load from before cover art finished
   generating and never retry. Fix: append `?v={created_at}` to
   `story_image_url`/`dj_image_url` in the gallery API response so a
   genuinely-updated image always gets a fresh URL.
4. **`harmonic_report.py` — add a `--set-order` flag** that, given a brain,
   suggests a reordering of `TRACKS` by key+BPM compatibility (print-only,
   never auto-edits the brain file — brains stay hand-curated per existing
   design).
5. **make_mix.py — surface the Camelot key of each curated track** in the
   printed tracklist (already computed by `get_or_analyze`, currently only
   printed during the build phase, not the curation-confirmation phase).
6. **Sync check script**: `mac_app/check_stale.py` — compares file hashes
   between `mixer/` and `mac_app/djbot_src/mixer/` (and `webapp/`) and
   warns if the packaged app copy has drifted from source, so the Aug 19
   staleness bug caught live today doesn't silently recur.
7. **Track-level "why this transition" annotation in SET_NOTES.txt** —
   the cue sheet already lists blend times; add one line per transition
   explaining which tier fired (beat-matched / bridged / hard-cut) and why,
   so a listener (or Louis) can understand a set's mix choices without
   reading the build log.
8. If time remains: small polish on the webapp's Surprise Me flow (e.g.
   surfacing the Camelot key alongside BPM in the live job view), same
   spirit as item 5 but in the web UI.

## Safety rules for the build loop

- One backlog item per 5-minute pass, smallest safe increment.
- Run `python -m pytest tests/test_set_quality.py -v -m "not slow"` after
  every change (fast, ~2s) before committing anything.
- Never touch `_band_split`, `_eq_blend`, `_bpm_ramp`, `_phase_error_ms`,
  `_build_hard_cut_transition`, or the amplitude-continuity check logic —
  those are correctness-critical and were already modified once today.
- Commit + push only on a clean test run. If a change can't be made safely
  in one pass, revert it and move to the next backlog item rather than
  leaving something half-done.
