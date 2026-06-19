# DJ Bot — Project Rules for Claude

## NON-NEGOTIABLE: Never corrupt the audio timeline
**These are the hardest rules. No feature, no technique, no "improvement" overrides them.**

1. **Never repeat audio.** If a section of a track plays once, it must not play again.
   Any code that appends audio from position X and then separately appends audio that
   overlaps or replays position X is a critical bug. Audit every concat in the assembly loop.

2. **Never skip audio.** A gap between where the body ends and where the blend picks up
   is a content hole. The transition must be gapless — body ends at sample N, blend A-side
   starts at sample N (or the exact equivalent position in the native-BPM version of the track).

3. **Never cut audio mid-phrase without a crossfade.** Every hard boundary (body→blend,
   blend→next body) must be either (a) a continuous read of the same audio array with no
   position jump, or (b) an equal-power crossfade with verified phase alignment.

**What caused repeats in the past:** A "preload" was added that played Butch's outro zone
(after body_end) for 3 seconds, then the pre-computed blend ALSO started from the same
position — playing the same musical content twice. User heard the repeat at 6:13 and 9:23.
Preload was removed entirely. Do not re-add any preload unless the start position is verified
to NOT overlap with the blend's A-side start.


## Non-negotiable quality gate
**Every transition MUST pass both checks before presenting to the user:**

1. **Phase error < 20ms** — measured by linear regression over all beats detected in the
   blend file (`_phase_error_ms(blend_path)` in set_builder.py). This is the ONLY reliable
   method — PRE/POST file approach has ±30ms noise from beat detector startup bias.

2. **Amplitude continuity < 3.0x RMS ratio** — checked at BOTH blend-in (blend_start) and
   blend-out (blend_end) using a 2-second window. Ratio = max(pre,post)/min(pre,post).
   Threshold 3.0x accounts for normal music dynamics over 2s; anything higher is a real cut.

If either check fails → fix it. Do not show the user a transition that fails.
Never report a transition as done without running both checks.


## Full mix assembly — how it works

### Structure of a mid-set track
```
[body_start ──────────────── body_end] [blend_audio] [next body_start ────]
         stretched B at A's BPM              ~31s           stretched B' at B's BPM
```

1. **Body**: `b_s[body_start : body_end]` — stretched B, continuous from prior blend-in
2. **Blend**: pre-computed equal-power crossfade — A fades out, B fades in over 16 bars
3. **Next body**: starts at `trim + cf_len` in the NEXT transition's `samples_b_s`

The body ends at EXACTLY the position where the pre-computed blend's A-side starts.
The next body starts at EXACTLY the position where the blend's B-side ends.
No gap. No overlap. No repeat.

### Body audio rule — CRITICAL
**Always use stretched B audio (`samples_b_s`) for the body section.**

- `b_s = tr_prev["samples_b_s"]` — B stretched to A's native BPM
- Continuous with how B was introduced in the blend-in. No BPM jump at blend-end.
- `body_start = tr_prev["trim"] + tr_prev["cf_len"]` — exact position where blend-in left off
- `body_end = outro_stretched` (capped at 180s, bar-snapped)

**NEVER switch to native B audio for body** — causes BPM jump at blend-END when the
incoming track takes over at 100% volume. User hears this as a "clear cut." Tested and
confirmed bad (caused the 3:32 cut in the solomun set).

### 5ms micro-crossfade at every body→blend splice — DO NOT REMOVE
The body uses stretched audio from the PREVIOUS transition's build (e.g., Butch at 122 BPM).
The blend's A-side uses native audio loaded fresh in the NEXT transition's build (e.g., Butch
at 124 BPM). Even when BPMs match, different processing chains produce different sample values
at the exact splice point → audible click ("blip") at the transition start.

Fix: crossfade the last 5ms of body into the first 5ms of blend:
```python
micro_n = int(0.005 * sr)
t = np.linspace(0.0, 1.0, micro_n)[:, np.newaxis]
b_body[-micro_n:] = b_body[-micro_n:] * (1.0 - t) + blend_audio[:micro_n] * t
blend_audio = blend_audio[micro_n:]
```
This is inaudible as a transition (5ms) but eliminates the waveform discontinuity.
Apply at every `elif idx < len(transitions)` body→blend join.

### Body cap: 3 minutes max
- `MAX_BODY_SEC = 180` — hard cap, bar-snapped to keep beats aligned
- If capped: recompute blend with `_reblend(b_s[body_end:], tr_next["b_full"], tr_next["cf_len"])`
- If not capped: use pre-computed `tr_next["blend"]` directly (already beat-verified)

### Last track
- `last_body = tr_prev["samples_b_s"][tr_prev["trim"] + tr_prev["cf_len"]:]`
- Play to the end — no blend needed


## The BPM jump problem — solved with gradual ramp

When consecutive tracks have DIFFERENT BPMs, there is always a BPM transition somewhere.
Three approaches were tested before finding the correct solution:

| Approach | BPM jump location | User perception |
|---|---|---|
| Stretched body + pre-computed blend (no ramp) | Blend-START (A at 100%, fading out) | "Slight issue" / rhythm jump |
| Native body + pre-computed blend | Blend-END (B at 100%, just took over) | **"Clear cut"** |
| Re-stretched B-side + stretched body | Blend-END content gap (0.49s skip) | **5x amplitude discontinuity** |

**Solution: BPM ramp over the last 8 bars of body.** Before the blend starts, gradually nudge
the body's playback speed from body BPM to blend-native BPM over 8 bars (≈16 seconds).
This is exactly what a real DJ does with the pitch control on CDJs.

### How the ramp works (in set_builder.py `_bpm_ramp`)
- Split the last `RAMP_BARS=8` bars of body into `RAMP_CHUNKS=32` chunks (~0.5s each)
- Each chunk gets a linearly interpolated stretch ratio: lerp(1.0, target_ratio, t)
  - Chunk 0 (t=0.015625): 0.05% change from body BPM — inaudible
  - Chunk 31 (t=0.984375): 98.4% of the way to blend native BPM
  - Step per chunk: ~0.06 BPM for a 2-BPM jump — completely imperceptible
- `target_ratio = tr_next["period_a"] / tr_prev["period_a"]`
  - < 1.0: compress (speed up toward blend BPM)
  - > 1.0: expand (slow down toward blend BPM)
- **5ms micro-crossfade at every chunk boundary** — eliminates waveform discontinuities
  from different pyrubberband calls; 31 boundaries × 5ms = 155ms total crossfade
- pyrubberband preserves beat positions within each chunk → phase-continuous at body→blend
- Only applied when NOT capped (capped bodies use `_reblend` at body BPM, no mismatch)
- `RAMP_THRESHOLD = 0.0` — ramp fires for ALL non-capped bodies, including same-nominal-BPM
  pairs where the beat detector gives slightly different period values. Inner guard in
  `_bpm_ramp` skips the pyrubberband call when |ratio-1| < 0.0001 (true no-op).

After the ramp, the existing 5ms micro-crossfade handles sample-level discontinuity at the
body→blend boundary as before.

### Why 4 chunks (RAMP_CHUNKS=4) was not enough
With 4 chunks of ~2 seconds each:
- Each boundary is a discrete BPM jump of ~0.5 BPM for a 2-BPM transition
- 4 audible rhythm steps within the ramp zone, instead of 1 jump at the blend
- User confirmed this was still audible at 6:11 after the first ramp implementation
With 32 chunks of ~0.5 seconds each:
- Each boundary is ~0.06 BPM — well below the perceptual threshold (~0.2 BPM)
- The crossfades between chunks eliminate any waveform discontinuity at each step

### Why RAMP_THRESHOLD = 0.0 (apply to ALL transitions)
Originally set to 0.01 (1%), which caught the major 2-4 BPM jumps. But the user heard
a rhythm issue at 9:21 (Sol body at Butch's 124 BPM entering Sol→Adana blend at Sol's
native 124 BPM). Even a 0.05% BPM difference from the beat detector produces a noticeable
rhythm stutter at the body→blend boundary. Setting threshold to 0.0 ensures EVERY transition
is ramped, with the inner guard making truly same-BPM pairs a no-op.

### Which transitions get ramped (solomun set)
| Track body | Body BPM → Blend BPM | Why |
|---|---|---|
| Butch_Lale | 122→124 | KT intro at 122, Butch native at 124 |
| Innellea | 123→120 | Patrice at 123, Innellea native at 120 |
| Wassermann | 120→124 | Innellea at 120, Wassermann native at 124 |
| Sol_Amanacer | 122→120 | GuyGerber at 122, Amanacer native at 120 |
| TubeNBerger | 120→122 | Amanacer at 120, TubeNBerger native at 122 |
| TaleOfUs | 123→125 | Adriatique at 123, TaleOfUs native at 125 |


## mix_in_bars — CRITICAL, must be tuned per track

`mix_in_bars` controls WHERE in the incoming track the blend enters.
**A bad mix_in_bars is the #1 cause of audible "cut in" artifacts.**

### How to choose mix_in_bars
- **Start with 0** — most house/techno tracks have a quiet 16–32 bar intro that blends in naturally
- If the blend-in sounds abrupt ("cuts into the middle of a song"), the mix point landed loud
- If the blend-in is smooth, the quiet section is at that bar count
- Try 0 → 8 → 16 → 32 and listen

### Symptoms of wrong mix_in_bars
- User says "cut in" or "something happening" at blend-start
- User says "sounds like cutting into the middle of the song"
- High blend-in RMS ratio in the amplitude report

### Known good settings (solomun set — do NOT change without testing)
| Track | mix_in_bars | Notes |
|---|---|---|
| KT_Sorry | 16 | first track |
| Butch_Lale | 32 | quiet 32-bar intro ✓ |
| Sol_Story | 32 | ✓ |
| Adana_Everyday | 0 | 32 was loud — fixed |
| Adana_Strange | 32 | quiet 32-bar intro ✓ |
| Brecht | 0 | 32 was loud — fixed |
| Ame_Fiori | 0 | 32 caused "trash" transition — fixed |
| Patrice_Serpent | 32 | ✓ |
| Innellea | 32 | quiet 32-bar intro ✓ |
| Wassermann | 32 | ✓ |
| Nicone | 32 | ✓ |
| GuyGerber | 32 | quiet 32-bar intro ✓ |
| Sol_Amanacer | 32 | ✓ |
| TubeNBerger | 32 | ✓ |
| Rampa_2000 | 32 | ✓ |
| Adriatique | 32 | ✓ |
| TaleOfUs | 32 | ✓ |
| Rampa_Touch | 8 | known good |
| Ame_Rej | 32 | ✓ |
| Stimming | 140 | last track — skip into outro section |


## Crossfade settings (solomun brain)
- CF_BARS = 16 — 16 bars ≈ 31s at 122 BPM
- OUTRO_BARS = 90 default; per-track overrides via `"outro_bars"` key in TRACKS list
- SNIPPET_SEC = 15 — snippet clips export 15s before and after blend for review

## Beat detection
- Primary: `beat_this` (CPJKU, `checkpoint='final0'`, `device='cpu'`, `dbn=False`)
- Anchor cache: `downloads/library/beatgrid_cache.json`
- Startup bias fix: feed the model 2 beats of audio BEFORE the target window
- Phase measurement: blend-file linear regression over ALL detected beats (mid-half residuals)
  Formula: fit line to beat timestamps → residuals → compare mean of first half vs second half

## Output structure
- `output/<set_name>/FULL_SET.mp3` — canonical full mix
- `output/<set_name>/SET_NOTES.txt` — tracklist + auto-generated cue sheet (actual blend times)
- `output/<set_name>/<n>_A_into_B.mp3` — per-transition snippet (15s pre + blend + 15s post)
- `output/transitions/` — raw build artifacts per pair (BLEND.mp3 for phase measurement)

## Cue sheet
Auto-generated from actual `blend_start`/`blend_end` sample positions — never hardcode times.
Strip any existing `── CUE SHEET` block from the brain's SET_NOTES before appending.

## Testing — run after every code change

```bash
# Fast unit tests only (no audio files, ~2s):
python -m pytest tests/test_set_quality.py -v -m "not slow"

# Full integration test — 3-track build (~60s):
python -m pytest tests/test_set_quality.py -v -m "slow" -k "ThreeTrack"

# Full solomun 20-track test (~10 min):
python -m pytest tests/test_set_quality.py -v -m "slow" -k "Solomun"
```

**test_set_quality.py covers:**
- 10 unit tests for `_bpm_ramp`: ratio=1.0 no-op, short body guard, stable section
  unchanged, speed-up shortens output, slow-down lengthens output, energy preserved,
  length matches average ratio, and the 3 constant values (BARS=8, CHUNKS=32, THRESHOLD=0.0)
- 7 unit tests for `_band_split` / `_eq_blend` (v2): bands sum to original, bass/high capture
  correct frequencies, output shape, no clipping, bass swap verified by correlation, USE_EQ_BLEND=True
- 8 integration tests for 3-track build: exit code, files exist, 2 phase errors < 20ms,
  no RMS cuts, ramp fires for Butch, ramp BPM values correct, snippets exported
- 12 integration tests for full solomun set: all 19 phase errors, no RMS cuts, ≥6 ramps,
  cue sheet has 19 entries, 19 snippets exist, duration 60–65 min, per-transition ramp checks


## History of problems solved (read before touching assembly code)

Every item below was a real user complaint that took multiple attempts to fix.
Before changing any assembly logic, verify your change doesn't re-introduce these.

| Time | Symptom | Root Cause | Fix Applied |
|---|---|---|---|
| 3:32 | Clear cut at end of KT→Butch blend | Body used native Butch audio → BPM jump at blend-END when B took over at 100% | Reverted to stretched body (`samples_b_s`) at all times |
| 6:13, 9:23 | Audio repeat — same section played twice | Preload played `b_s[body_end : body_end+n]`, then blend replayed same position | Removed preload entirely. Do not re-add. |
| 9:19, 15:09, 18:05–18:37 | Abrupt "cut in" at blend-start | `mix_in_bars=32` landed in loud section of Adana/Brecht/Ame_Fiori | Set `mix_in_bars=0` for those tracks |
| (all blends) | Waveform click/blip at body→blend splice | Different processing chains (stretched vs native) give different sample values at exact splice | 5ms micro-crossfade at every `elif idx` body→blend boundary — DO NOT REMOVE |
| 6:10, 9:19 | 5.21× amplitude spike at blend-start | `outro_stretched` computed wrong: `outro_sample × len(b_s)/len(native_full)` ignores cue_b offset. When B-track has cue point C, b_s starts at C in native B, so correct formula is `(outro_sample - C) × stretch_ratio`. Wrong formula made body end too late (in a quiet breakdown past the real outro point); blend then jumped to loud outro_sample. Fixed by storing `cue_b` and `stretch_ratio` in the build dict and using them in assembly. |
| 6:11 | Rhythm jump at Butch blend-start | Butch body at 122 BPM, blend A-side switched to Butch native 124 BPM | BPM ramp over last 4 bars (122→124 gradual, 4 chunks) |
| 9:21 | Rhythm issue at Sol→Adana blend-start | Even same-nominal-BPM pairs have slightly different detector periods → tiny jump | Lowered RAMP_THRESHOLD to 0.0 (ALL non-capped bodies get ramped) |
| (discovery) | phase error measurement unreliable ±30ms | PRE/POST file approach has beat-detector startup bias | Switched to blend-file linear regression (±1ms accuracy) |
| (discovery) | 5x RMS discontinuity at some blend-outs | Re-stretching B-side of blend → `cf_len / restretch ≠ cf_len` → wrong body_start next track | Never re-stretch the blend's B-side; body_start = `trim + cf_len` always |
| 22:49 | "Starts matched then gets unmatched" during AmeF→Patrice blend | Capped AmeF body plays at 120 BPM; `_reblend` used `b_full` at AmeF's native 122.984 BPM → 386ms BPM drift by blend midpoint | For capped bodies with BPM mismatch (>0.1%): ramp body to native BPM, convert body_end to native coords, snap to native bar, use `samples_a[native_bar_end:]` as A-side of `_reblend`. Store `anchor_b_s` in build dict. Also fires for Adana_Everyday (124→120 BPM). |
| 19:17, 22:49 | "Off by a beat" at capped-body transitions (Brecht→AmeF, AmeF→Patrice) | `body_end` was snapped forward from `body_start` by whole bars (`body_start + N*bar_len`). `outro_stretched` can be 1–3 beats into a bar; B's trim was aligned to `outro_stretched`'s bar phase, not to body_end's bar phase → B arrives 1–3 beats off within its bar | Snap `body_end` BACKWARD from `outro_stretched` in whole-bar steps (`outro_stretched - k*bar_samples`) so body_end has the same bar phase as outro_stretched. Same for `native_bar_end` in the BPM-mismatch case. |
| (improvement) | Offset selection optimized for beat regularity only — phase drift ignored | ±1-beat search picked offset by minimum beat CV but didn't penalize BPM drift during blend | Combined score: `cv + 0.3 * min(phase_ms, 40) / 20` — keeps CV dominant, adds 0.3 CV-point penalty for 20ms phase drift. Computed inline from beats already detected. |


## What NOT to do (approaches tested and rejected)
- **Preload (B fading in before body_end):** Causes REPEAT — preload plays audio from after
  body_end, which is the same audio the blend's A-side then replays. User heard repeat at
  6:13 and 9:23. Do not re-add unless start position is provably non-overlapping.
- **Re-stretching B-side of blend** to match A's BPM → content gap at blend-out (≥5x RMS).
- **Native B body** → BPM jump at blend-END (user heard as "clear cut" at 3:32).
- **PRE/POST phase measurement** → ±30ms noise from beat detector startup bias.
- **body_start_override** → made amplitude worse (5.02x) by landing at a quieter position.
- **RAMP_THRESHOLD > 0** → misses same-nominal-BPM pairs with slight detector differences,
  leaving a rhythm stutter at those transition boundaries (user heard at 9:21).
- **Stretching Demucs stems independently (v2 research finding):** Do NOT time-stretch
  drums/bass/other stems separately with pyrubberband then re-sum. pyrubberband's phase vocoder
  introduces per-frequency-bin phase rotations that differ per stem → comb filtering at 60–120 Hz
  (exactly where kick/sub-bass overlap). The re-summed audio sounds thin and hollow. Only stretch
  the FULL mix; then apply EQ filtering on the already-stretched blend zone.
- **Drum-stem beat detection (v2 research finding):** Running beat_this on a Demucs drum stem does
  NOT improve phase accuracy. beat_this was trained on full-mix audio — feeding it an isolated drum
  stem is out-of-distribution. Our 2–8ms phase errors are already below what academic papers target.


## v2 — EQ-style per-band crossfade (branch: v2-stem-mixing)

### What it does

Instead of a uniform equal-power crossfade across all frequencies, v2 applies **Pioneer DJM-800
frequency band curves** to the blend zone. Research finding: the biggest perceptual improvement
in DJ transitions is eliminating bass clash (two kick+sub-bass signals simultaneously producing
comb filtering at 60–120 Hz).

### Signal flow

```
Full track A → time-stretch (pyrubberband) → samples_a
Full track B → time-stretch to A's BPM    → samples_b_s
Select blend zone via offset search (beat CV + phase score) [equal-power for measurement]
After offset + drift correction are locked:
  A blend zone = samples_a[outro_sample : outro_sample + n]
  B blend zone = samples_b_s[trim : trim + n]
  _band_split(A zone) → (A_bass, A_mid, A_high)   [IIR zero-phase, lossless]
  _band_split(B zone) → (B_bass, B_mid, B_high)
  A_bass * logistic_out(p) + B_bass * logistic_in(p)   ← sigmoid swap at 50 %
  A_mid  * equal_power_out(p) + B_mid  * equal_power_in(p)
  A_high * equal_power_out(p) + B_high * equal_power_in(p)
  → sum → clip to [-1, 1] → best["blend"]
```

### Key implementation facts

- **Bands:** bass = 0–200 Hz (4th-order Butterworth LPF), high = 5 kHz+ (HPF), mid = A − bass − high.
  `bass + mid + high == audio` exactly (no energy loss or overlap artifacts).
- **Bass swap:** logistic (sigmoid) centered at 50% of blend, width w=0.12 (≈3.7 s at 31 s blend ≈2 bars).
  Short enough to avoid prolonged comb filtering; not a hard cut, so no click.
- **Measurement blends** (offset loop, drift correction) still use equal-power so beat_this CV/phase
  scores are clean and unaffected by the EQ curves.
- **`_reblend`** (used for capped bodies) also uses `_eq_blend`. Falls back to equal-power when
  `USE_EQ_BLEND = False`.
- **`USE_EQ_BLEND`** flag at module level — set `False` to revert to v1 equal-power for A/B comparison.

### Files changed in v2

- `mixer/set_builder.py` — added `_band_split`, `_eq_blend`, `USE_EQ_BLEND`; updated `_reblend`;
  applied EQ blend after offset/drift selection, before export.
- `mixer/stems.py` — Demucs htdemucs wrapper, cached npz. Available for future experiments but
  NOT used in the main blend path (stretching stems independently breaks phase coherence).
- `tests/test_set_quality.py` — 7 new unit tests: band_split sums to original, bass/high capture
  correct frequencies, shape, no clipping, bass swap verified by correlation, USE_EQ_BLEND=True.

### Perceptual improvement expected

- Bass clash eliminated — one kick at a time through the blend.
- Melody (mid/high) transitions smoothly with standard equal-power.
- Phase accuracy unchanged (still measured and enforced at < 20ms).
- The "starts matched then gets unmatched" complaint may be partially masked by the EQ swap —
  phase errors above 6ms are most audible when both bass lines are simultaneously present.
