# djbot — new features plan (2026-09-05)

Continuation of yesterday's 8-item backlog (all shipped — see
NEW_FEATURES_PLAN_2026-09-04.md and git log a61d81b..ac96714). This session
picks up the loose threads that plan explicitly left open, plus a couple of
new items. Same safety rules as yesterday.

## Where things stand (checked live at session start)

- `mac_app/check_stale.py` (built yesterday) now reports **5 stale files +
  1 missing entirely** in the packaged app — everything touched yesterday,
  including today's own webapp UI change. Never actually re-synced/rebuilt.
- CLAUDE.md gained a new global HARD RULE yesterday (2026-09-04, appeared
  on disk just now): every UI change must be checked at a real mobile
  viewport (~375-390px) via `mcp__playwright__browser_resize`, not just a
  desktop screenshot — before calling it done. Yesterday's job-view key
  display change (item 8) was never checked at mobile width. Retroactive
  compliance is item 1.
- The gallery image cache-busting fix (yesterday's item 3) is still sitting
  on disk only — djbot-gallery had no git repo and no confirmed deploy path
  at the time. Railway CLI access got fixed account-wide yesterday
  (full login, not a single-project token) — worth re-checking whether
  `railway up` actually works there now before assuming it's still blocked.
- The hard-cut amplitude/loudness-jump issue (flagged 2026-09-04, T02→T03
  in the "gothic post-punk meets techno" mix, 8.43x RMS) is still open.
  Real, but correctness-critical territory — treated as a stretch item
  here, not a guaranteed 5-minute fix.

## Backlog (in build order)

1. **Mobile-viewport check of the webapp job-view UI** (retroactive
   compliance with the new HARD RULE). Use `mcp__playwright__browser_resize`
   to a real mobile width, screenshot the job view (`.track-row`,
   `.track-bpm`), fix anything that overflows/clips/crushes.
2. **Sync `mac_app/djbot_src/`** from source using `check_stale.py`'s exact
   file list, then re-run `check_stale.py` to confirm it reports clean.
3. **Re-check djbot-gallery deploy access.** Now that Railway login is
   account-wide, try `railway status`/`railway up` from djbot-gallery
   again — if it actually works this time, ship the image cache-busting
   fix that's been sitting on disk since yesterday.
4. **If item 3 unblocks deploy**, run `mac_app/build_signed_app.sh` against
   the now-synced djbot_src, host the resulting zip + bump
   `MAC_APP_VERSION` in djbot-gallery/app.py, and verify `/api/app-version`
   live reflects it — the actual proof yesterday's promised app rebuild is
   real, not just "done" on paper.
5. **Fix the stale beatgrid cache.** `downloads/library/beatgrid_cache.json`
   is keyed by absolute path and still has the old `Desktop/vibe/djbot`
   prefix from before this project moved — every real brain (solomun,
   etc.) currently gets zero cache hits. Add a one-off migration that
   rewrites old-prefixed keys to the new location where the file still
   exists at that path, recovering already-computed analysis instead of
   wasting it on the next real build.
6. **`make_mix.py --dry-run`**: print the curated tracklist (with BPM/key
   once analyzed) and estimated track count/cost without downloading or
   building anything — lets Louis preview a request before committing to
   a real (paid curation + slow) build.
7. **Stretch, handle carefully:** investigate the hard-cut loudness-jump
   issue. This touches `_build_hard_cut_transition` — normally off-limits
   in this loop, but a full day has passed since the original fix landed
   and it's tested/pushed. Any change here needs the same rigor as the
   rest of that file: small increment, full fast-suite pass, and an
   explicit "not safely fixable in one 5-minute pass" bail-out if there's
   any doubt. Do not force it.
8. **`djbot-gallery` — `git init`** if item 3 confirms Railway deploy access
   works there now. Makes it a normal git-tracked project instead of a
   permanent special case for every future gallery change.

## Round 2 backlog (same day, continued session)

Items 1-8 above are resolved: 6 shipped (2,3,4,5,6,8), item 7 deliberately
declined (see below — no safe way to validate a hard-cut audio change by
ear), item 1 blocked on a Playwright tooling hang (3 attempts, all hung
120s+ including a bare resize with no page loaded — not retried further
per the "don't hammer a failing tool" rule).

9. **Retry item 1 once**, now that time has passed — a real mobile-viewport
   check of the webapp job view. If Playwright hangs again, stop and flag
   it as a real environment issue rather than retrying further.
10. **Safe alternative to the declined item 7**: instead of changing hard-cut
    audio processing (unvalidatable without listening), extend the item-7
    cue-sheet tier annotation to flag when a transition's own amplitude-
    continuity check failed — read-only visibility into a known issue,
    zero audio risk, same spirit as the rest of item 7.
11. **Extend `check_stale.py` to also cover `windows_app/djbot_src/`** —
    the Mac app just got fixed; the Windows copy has had zero attention
    and is presumably in the same stale state.
12. **Wire the harmonic re-sort into `webapp/job_runner.py`** (not just
    surfacing the key, per item 8's explicit descope) — now that
    make_mix.py's `_harmonic_resort` is proven (6 tests, shipped, no
    incidents), apply the same soft re-sort to the webapp's Surprise Me
    flow. Import and reuse make_mix.py's function; don't reimplement.
13. **djbot-gallery**: add a minimal smoke test (`python -m py_compile
    app.py` + a lightweight import/route-count check) now that it's a real
    repo — closes the "no test suite here" gap for future changes.
14. If time remains: small polish pass — anything else `check_stale.py` or
    a fresh look at the codebase turns up.

## Safety rules (same as yesterday)

- One backlog item per 5-minute pass, smallest safe increment.
- Run `python -m pytest tests/test_set_quality.py tests/test_make_mix.py -v
  -m "not slow"` after every djbot-repo change before committing.
- Never touch `_band_split`, `_eq_blend`, `_bpm_ramp`, `_phase_error_ms`,
  or the amplitude-continuity check logic. `_build_hard_cut_transition`
  is allowed ONLY for item 7, with extra scrutiny, and only if it can be
  done safely in one pass.
- Commit + push only on a clean test run (djbot repo). djbot-gallery has
  no test suite — verify with syntax checks + code review there, same as
  yesterday, unless item 3 confirms deploy access, in which case a live
  `/health`/`/api/app-version` check after deploy is the real proof.
