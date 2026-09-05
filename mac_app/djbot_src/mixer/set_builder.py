"""
Core DJ set builder — shared engine used by all brain modules.

Call build_full_set(brain) where brain is any module (or object) that exposes:
  SET_NAME   str      — output folder name under output/
  SET_NOTES  str      — creative text written to SET_NOTES.txt
  TRACKS     list     — list of track dicts: {name, label, path, hint, mix_in_bars}
  CF_BARS    int      — crossfade length in bars (default 8)
  OUTRO_BARS int      — how many bars from end of A to start blend (default 16)
  SNIPPET_SEC int     — half-length of transition clip in seconds (default 6 → 12s total)
"""
import os, sys, math, random, tempfile, json
import numpy as np
from pydub import AudioSegment

from mixer.beatgrid import get_or_analyze, snap_to_beat
from mixer.transition import (
    _seg_to_f32, _f32_to_seg, _equal_power,
    find_cue_point, _time_stretch_samples, _beat_this_phase_trim,
    _mono,
)

PHASE_THRESHOLD_MS = 20.0

# Onset-regularity gate (2026-08-19) — a third, independent check alongside
# phase_err_ms/shipped_phase_err_ms. Beat-matching correctness is the top
# priority for this project (see CLAUDE.md) — a transition that passes the
# beat_this-based phase checks can still have audibly clashing beats, e.g.
# once the EQ-blend's bass-swap sigmoid reveals a kick-pattern mismatch that
# beat_this itself doesn't register as a phase error. Onset density/spacing
# in the actual shipped blend audio is a cheap, independent second opinion:
# a genuinely beat-matched blend has one steady onset grid; overlapping,
# unmatched beats show up as irregular inter-onset intervals (a mix of very
# short and very long gaps instead of one consistent spacing). Calibrated
# against real transitions (2026-08-19): a confirmed-bad transition measured
# CV=0.50 in the second half of its blend (past the bass-swap midpoint);
# confirmed-good transitions measured 0.31-0.41. Threshold set at 0.45 —
# conservative, catches the confirmed-bad case without flagging the
# confirmed-good ones. This is a noisier signal than the phase-error checks
# (small sample size, real per-song variation in onset density) — treat it
# as "when in doubt, prefer the hard cut" per the project's explicit
# priority, not as a precise measurement.
ONSET_CV_THRESHOLD = 0.45


def _onset_regularity_ok(blend_audio, sr):
    """
    True if the second half of the blend (past the EQ-blend bass-swap
    midpoint — see USE_EQ_BLEND/_eq_blend) has a sufficiently regular onset
    pattern. Returns True (pass) on any analysis failure — this is a
    best-effort second opinion, never the sole reason a whole track fails
    to build.
    """
    try:
        import librosa
        mono = blend_audio.mean(axis=1) if blend_audio.ndim == 2 else blend_audio
        half = len(mono) // 2
        second_half = mono[half:]
        if len(second_half) < sr * 2:  # too short to measure meaningfully
            return True
        onset_env = librosa.onset.onset_strength(y=second_half, sr=sr, hop_length=256)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=256, backtrack=False)
        if len(onset_frames) < 8:
            return True
        onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=256)
        iois = np.diff(onset_times) * 1000
        cv = float(np.std(iois) / np.mean(iois))
        return cv <= ONSET_CV_THRESHOLD
    except Exception:  # noqa: BLE001 — never block a build over this check itself erroring
        return True

# "Bridge" transitions: when two tracks' native BPMs are too far apart to blend
# directly (> max_bpm_diff_pct, default 8%), meet in the middle instead of hard-
# failing — the real DJ technique of walking the tempo. Above this outer ceiling,
# even bridging isn't musically sensible and the transition still hard-fails.
MAX_BRIDGE_DIFF_PCT = 35.0

# Within the bridge range, the far end forces the most aggressive time-stretch
# to lock a beat-matched blend (e.g. a 30%+ gap) — almost certainly the most
# audible pitch/tempo artifact in the whole tier system (see CLAUDE.md's HARD
# RULE, 2026-08-19: beat-matching correctness is the priority, and a forced-
# but-wrong-sounding stretch is worse than admitting the beats won't lock).
# Above this threshold, fall back to a plain crossfade at each track's own
# native tempo — no forced stretch, no beat lock attempted — same philosophy
# as the hard-cut fallback below, applied one tier earlier, with a softer
# landing (crossfade, not echo+splice) since tracks in this sub-range are
# still close enough that an unmatched crossfade doesn't clash the way a
# >MAX_BRIDGE_DIFF_PCT hard cut would.
#
# Scoped 2026-08-28 (SCOPING_2026-08-28.md), built 2026-08-28. Conservative
# default: biased toward keeping the existing bridged-beatmatch behavior for
# the lower half of the bridge range (8-20%); only the upper half (20-35%)
# gets the new crossfade fallback. NOT YET VALIDATED BY EAR against real
# material in this diff_pct range — CLAUDE.md is explicit that a passing gate
# (or, here, the absence of one) isn't proof of a good-sounding transition.
# Retune this threshold (or revert to always-bridge) if a real transition in
# the 20-35% range is listened to and sounds wrong either way.
SOFT_CROSSFADE_THRESHOLD_PCT = 20.0

# v2: per-band EQ crossfade (Pioneer DJM-800 style).
# True  → bass swaps at 50 % of blend, highs+mids use equal-power.
# False → original uniform equal-power throughout (v1 behaviour).
USE_EQ_BLEND = True


# ── EQ blend helpers ──────────────────────────────────────────────────────────

def _band_split(audio, sr):
    """
    Split stereo [T,2] audio into (bass, mid, high) bands using zero-phase IIR
    filters at 200 Hz and 5 kHz. bass + mid + high == audio exactly.
    """
    from scipy.signal import butter, sosfiltfilt
    nyq = sr / 2.0
    sos_lo = butter(4, 200.0 / nyq, btype='low',  output='sos')
    sos_hi = butter(4, 5000.0 / nyq, btype='high', output='sos')
    bass = sosfiltfilt(sos_lo, audio, axis=0).astype(np.float32)
    high = sosfiltfilt(sos_hi, audio, axis=0).astype(np.float32)
    mid  = (audio - bass - high).astype(np.float32)
    return bass, mid, high


def _eq_blend(za, zb, n, sr):
    """
    DJ-style per-band EQ crossfade.

    High + Mid : standard equal-power crossfade over the full 16-bar blend.
    Bass       : logistic (sigmoid) swap centred at 50 % of blend, ~3.7 s wide
                 at a 31 s blend.  Avoids two sub-bass signals fighting for
                 3–10 seconds and causing comb filtering in the 60–120 Hz range.

    Measurement blends (offset search, drift correction) still use equal-power so
    that beat_this CV and phase scores are clean.  This function is called only
    once, AFTER the best blend position is selected.
    """
    n  = min(n, len(za), len(zb))   # guard against end-of-file truncation
    za = za[:n].astype(np.float32)
    zb = zb[:n].astype(np.float32)

    a_bass, a_mid, a_high = _band_split(za, sr)
    b_bass, b_mid, b_high = _band_split(zb, sr)

    p = np.linspace(0.0, 1.0, n, dtype=np.float32)

    ep_out = (np.cos(p * (np.pi / 2.0)) ** 2).reshape(-1, 1)   # A: 1 → 0
    ep_in  = (np.sin(p * (np.pi / 2.0)) ** 2).reshape(-1, 1)   # B: 0 → 1

    # Widened 2026-08-18 from 0.12 (2.7x faster than equal-power at the midpoint)
    # to 0.20 (~1.6x faster) — the sharper swap was confirmed, via real beat_this
    # analysis on a delivered mix, to leave a measurable single-beat timing
    # discontinuity (560ms vs a steady ~460ms pattern) exactly at the blend
    # midpoint. Still faster than equal-power (keeps most of the bass-clash
    # protection this technique exists for), just less abrupt.
    w = 0.20
    a_bass_g = (1.0 / (1.0 + np.exp((p - 0.5) / w))).reshape(-1, 1)
    b_bass_g = 1.0 - a_bass_g

    blend = (
        a_bass * a_bass_g + b_bass * b_bass_g +
        a_mid  * ep_out   + b_mid  * ep_in    +
        a_high * ep_out   + b_high * ep_in
    )
    return np.clip(blend, -1.0, 1.0)


# BPM ramp defaults — applied to every non-capped body at every body→blend boundary.
# Set RAMP_THRESHOLD = 0.0 so the ramp fires for ALL transitions, including same-nominal-BPM
# pairs whose beat detectors give slightly different period values. Inner guard inside
# _bpm_ramp skips the pyrubberband call when |ratio-1| < 0.0001 (true no-op case).
RAMP_BARS      = 8     # bars to ramp over before the blend (~16s at 122 BPM)
RAMP_CHUNKS    = 32    # kept for API compat; not used in continuous-resample path
RAMP_THRESHOLD = 0.0   # apply ramp to ALL non-capped bodies


# ── BPM ramp helper ──────────────────────────────────────────────────────────

def _bpm_ramp(b_body, sr, target_ratio, body_period,
              ramp_bars=None, ramp_chunks=None):
    """
    Gradually ramp the last ramp_bars bars of b_body from its playing BPM toward the
    blend's native BPM using continuous linear resampling.

    target_ratio = blend_native_period / body_period:
      < 1.0 → compress (speed up body to reach a higher blend BPM)
      > 1.0 → expand  (slow  down body to reach a lower  blend BPM)
      = 1.0 → true no-op (returns b_body unchanged)

    How it works:
      Reads the ramp section at a continuously varying playback rate that linearly
      interpolates from 1.0 (body BPM) to 1/target_ratio (blend BPM). This avoids
      chunk boundaries entirely — no discrete BPM steps, no pyrubberband startup
      artifacts at each boundary.

      For output sample i in [0, n_out):
        advance_rate(i) = 1.0 + (1/target_ratio - 1.0) × i/n_out
        input_pos(i)    = i + (1/target_ratio - 1.0) × i² / (2 × n_out)
        n_out           = int(round(n_in × 2 × target_ratio / (1 + target_ratio)))

      This changes playback speed and pitch simultaneously (like CDJ without keylock).
      The pitch shift is ≤ 0.3 semitones total over the ramp, which is imperceptible.

    ramp_chunks is accepted but ignored (kept for API compatibility with tests).
    Module-level so tests can import and call it with synthetic audio.
    """
    if ramp_bars is None:
        ramp_bars = RAMP_BARS

    ramp_n = int(round(ramp_bars * 4 * body_period))
    if len(b_body) <= ramp_n + int(body_period):
        return b_body  # body too short; skip ramp

    if abs(target_ratio - 1.0) <= 0.0001:
        return b_body  # true no-op

    stable  = b_body[:-ramp_n]
    ramp_in = b_body[-ramp_n:]
    n_in    = len(ramp_in)

    # Output length: integrate advance_rate from 0 to n_out to consume exactly n_in samples.
    # advance_rate goes from 1.0 to inv_r = 1/target_ratio linearly.
    # Integral: n_out + (inv_r - 1) × n_out / 2 = n_in  →  n_out = 2×n_in×r / (1+r)
    inv_r = 1.0 / target_ratio
    n_out = max(1, int(round(n_in * 2.0 * target_ratio / (1.0 + target_ratio))))

    # Input position for each output sample (quadratic accumulation of linear rate)
    i_vec     = np.arange(n_out, dtype=np.float64)
    input_pos = i_vec + (inv_r - 1.0) * i_vec * i_vec / (2.0 * n_out)
    input_pos = np.clip(input_pos, 0.0, n_in - 1.0 - 1e-9)

    # Linear interpolation
    idx0 = input_pos.astype(np.int64)
    idx1 = np.minimum(idx0 + 1, n_in - 1)
    frac = (input_pos - idx0).astype(np.float32)
    if ramp_in.ndim > 1:
        frac = frac[:, np.newaxis]
    ramp_out = (ramp_in[idx0] * (1.0 - frac) + ramp_in[idx1] * frac).astype(np.float32)

    return np.concatenate([stable, ramp_out])


def _bpm_ramp_in(b_body, sr, target_ratio, native_period, ramp_bars=None, ramp_chunks=None):
    """
    Mirror image of _bpm_ramp: ramps the FIRST ramp_bars bars of b_body FROM a
    bridged tempo back TO its own native tempo (native_period), then continues at
    native tempo for the rest of the body. Used right after a bridged transition,
    where the incoming track was met at a midpoint BPM for the blend and needs to
    settle back to its true tempo once the crossfade is behind it.

    target_ratio = bridged_period / native_period — same new-over-old convention
    as _bpm_ramp's target_ratio, just describing where the HEAD starts relative to
    the native (stable) reference instead of where the tail needs to arrive.

    Implemented by reversing the buffer, running the well-tested _bpm_ramp (which
    ramps a tail) with native_period as the stable reference, then reversing back —
    exactly mirrors _bpm_ramp's math with zero duplicated logic.
    """
    reversed_out = _bpm_ramp(b_body[::-1].copy(), sr, target_ratio, native_period,
                              ramp_bars, ramp_chunks)
    return reversed_out[::-1].copy()


# ── Phase measurement ─────────────────────────────────────────────────────────

def _phase_error_ms(blend_path):
    """Blend-file linear regression — ±1ms accuracy, no PRE/POST startup bias."""
    try:
        from beat_this.inference import File2Beats
        beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(blend_path)
    except Exception:
        return None
    if len(beats) < 6:
        return None
    beats = np.array(beats, dtype=float)
    n = len(beats)
    i = np.arange(n, dtype=float)
    coeffs, _, _, _ = np.linalg.lstsq(
        np.column_stack([np.ones(n), i]), beats, rcond=None
    )
    anchor_fit, period_fit = coeffs
    residuals = beats - (anchor_fit + i * period_fit)
    mid = n // 2
    err = float(np.mean(residuals[mid:])) - float(np.mean(residuals[:mid]))
    while err >  period_fit / 2: err -= period_fit
    while err < -period_fit / 2: err += period_fit
    return round(abs(err) * 1000, 1)


# ── Single transition builder ─────────────────────────────────────────────────

def _octave_match(bpm_ref, bpm_other, period_other, tol_pct):
    """
    Fast breakbeat genres (jungle, drum & bass) are routinely beat-detected at
    their raw hit-rate (~170-180 BPM) but are actually felt and DJ-mixed at half
    that (~85-90 BPM) — the classic half-time/double-time ambiguity. Before
    treating two tracks as genuinely tempo-incompatible, check whether bpm_other
    is really just bpm_ref at the wrong octave (0.5x or 2x) and, if so, return
    the corrected (bpm, period) for `other`. Returns None if neither octave is
    within tolerance of bpm_ref.
    """
    for mult in (0.5, 2.0):
        cand_bpm = bpm_other * mult
        if abs(cand_bpm - bpm_ref) / bpm_ref * 100 <= tol_pct:
            return cand_bpm, period_other / mult
    return None


ECHO_OUT_BEATS = 4        # total decay window for a hard-cut echo-out, in beats
ECHO_DELAY_BEATS = 0.5    # spacing between echo repeats
ECHO_DECAY = 0.65         # gain multiplier per repeat
CLICK_GUARD_MS = 5        # tiny fade-in on B's very first samples — avoids a
                          # click from a non-zero-crossing edit; inaudible as a
                          # delay, not a real crossfade (B still "starts right away")

MAX_OUTRO_FRACTION = 0.5  # the outro window can never eat more than half a track


def _echo_out_tail(pre_cut_audio, sr, period_a, total_beats=ECHO_OUT_BEATS,
                    delay_beats=ECHO_DELAY_BEATS, decay=ECHO_DECAY):
    """
    Classic DJ "echo out" for a hard cut: repeats a short slice of A's audio
    right before the cut point at a fixed sub-beat delay with decreasing gain,
    so the outgoing track rings out and decays instead of stopping dead or
    needing a beat-matched crossfade. The incoming track starts immediately,
    at full volume, from the same position — this tail gets SUMMED on top of
    it, not faded in front of it, so there's no dead-air gap between tracks.
    Returns an array up to total_beats*period_a samples long (shorter only if
    gain decays below audibility first).
    """
    delay_n = max(1, int(round(delay_beats * period_a)))
    total_n = int(round(total_beats * period_a))
    src = pre_cut_audio[-delay_n:] if len(pre_cut_audio) >= delay_n else pre_cut_audio
    out = np.zeros((total_n, 2), dtype=np.float32)
    gain, start = 1.0, 0
    while start < total_n and gain > 0.02:
        end = min(start + len(src), total_n)
        seg_len = end - start
        if seg_len > 0:
            out[start:end] += src[:seg_len] * gain
        gain *= decay
        start += delay_n
    return out


def _safe_outro_bars(requested_outro_bars, period_a, total_samples):
    """
    OUTRO_BARS defaults (commonly 90, per CLAUDE.md's documented solomun-brain
    settings) are tuned for long house/techno tracks (7-8+ min) — reserving a
    90-bar window near the end for the transition. Applied to a much shorter
    track (a ~4:19 pop song, say), that same window can swallow almost the
    whole thing, leaving a near-zero body. Confirmed live 2026-08-18: "The
    Beatles - Come Together" (82.8 BPM, ~4:19) with OUTRO_BARS=90 computed a
    4:21 outro window — longer than the track itself — so its body came out
    as 0 seconds and the track was effectively silent/absent from the mix.
    Clamp so the outro window never exceeds MAX_OUTRO_FRACTION of the track,
    halving the bar count as needed until it fits (rather than a single hard
    clamp to some sample count, which would break bar-alignment downstream).
    """
    bars = requested_outro_bars
    while bars > 1 and bars * 4 * period_a > total_samples * MAX_OUTRO_FRACTION:
        bars = bars / 2
    return max(1, bars)


def _build_hard_cut_transition(track_a, track_b, out_dir, outro_bars, bpm_a, bpm_b,
                                period_a, period_b, anchor_a):
    """
    For pairs too far apart in tempo for even a tempo bridge (> MAX_BRIDGE_DIFF_PCT):
    no beat-matching at all — find a natural end point in A (its own outro, snapped
    to ITS OWN beat grid — same logic as a normal transition's outro point, just
    with no dependency on B's tempo) and a natural start point in B (find_cue_point,
    already used everywhere else to skip intro silence), then splice with a short
    fade to avoid a click. Real DJ technique for genuinely incompatible material —
    a clean hard cut on a beat beats a forced, badly-stretched blend.

    Returns a dict with the same keys build_one_transition returns, so the
    assembly loop in build_full_set needs no structural changes to consume it —
    just guards (via tr["hard_cut"]) to skip the beat-matching-specific logic
    (phase gate, BPM ramps) that doesn't apply here.
    """
    seg_a = AudioSegment.from_file(track_a["path"]).set_channels(2)
    seg_b = AudioSegment.from_file(track_b["path"]).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    effective_outro_bars = _safe_outro_bars(
        track_a.get("outro_bars", outro_bars), period_a, len(samples_a))
    outro_target = len(samples_a) - effective_outro_bars * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    outro_sample = max(0, min(outro_sample, len(samples_a)))

    cue = find_cue_point(seg_b)
    b_full = samples_b[cue:]

    # Echo the outgoing track out over ECHO_OUT_BEATS while the incoming track
    # starts immediately underneath, at full volume, from its own natural start
    # point — no dead-air gap, no beat-matched crossfade needed. Classic DJ
    # "echo out" move for material too different to blend cleanly.
    echo_tail = _echo_out_tail(samples_a[:outro_sample], sr, period_a)
    echo_n = min(len(echo_tail), len(b_full))
    b_head = b_full[:echo_n].copy()
    # Tiny click-guard fade-in on B only — inaudible as a delay, just prevents
    # a pop from splicing at a non-zero-crossing sample.
    guard_n = min(int(sr * CLICK_GUARD_MS / 1000), echo_n)
    if guard_n > 0:
        g = np.linspace(0.0, 1.0, guard_n)[:, np.newaxis]
        b_head[:guard_n] *= g
    blend = np.clip(echo_tail[:echo_n] + b_head, -1.0, 1.0)
    b_full = b_full[echo_n:]

    tag = f"{track_a['name']}_into_{track_b['name']}"
    print(f"    [hard-cut] {bpm_a:.1f} vs {bpm_b:.1f} BPM — too far apart even for a "
          f"tempo bridge; echoing A out over {ECHO_OUT_BEATS} beats while B starts "
          f"immediately underneath")

    return {
        "tag": tag, "bpm_a": bpm_a, "bpm_b": bpm_b, "phase_err_ms": None,
        "shipped_phase_err_ms": None, "onset_ok": True,
        "samples_a": samples_a, "samples_b_s": samples_b, "outro_sample": outro_sample,
        "cf_len": echo_n, "trim": cue, "blend": blend, "b_full": b_full, "sr": sr,
        "period_a": period_a, "cue_b": int(cue), "stretch_ratio": 1.0,
        "anchor_b_s": float(anchor_a),  # unused for hard cuts; kept for key compat
        "bridged": False, "native_period_a": period_a, "native_period_b": period_b,
        "hard_cut": True,
    }


def _build_soft_crossfade_transition(track_a, track_b, out_dir, outro_bars, cf_bars,
                                      bpm_a, bpm_b, period_a, period_b, anchor_a):
    """
    For pairs in the upper part of the "bridge" range (SOFT_CROSSFADE_THRESHOLD_PCT
    < diff_pct <= MAX_BRIDGE_DIFF_PCT): too far apart to force a clean-sounding
    beat-matched blend, but close enough that a full hard-cut+echo feels overly
    abrupt. Plain crossfade (EQ-band if USE_EQ_BLEND, else equal-power) at each
    track's own native tempo — no time-stretch of A, no forced beat lock
    attempted. Same outro/cue-point logic as _build_hard_cut_transition; only
    the blend content differs (a real crossfade instead of an echo-out +
    immediate B headstart).

    Deliberately reuses the "hard_cut": True contract: build_full_set's Pass 1
    loop treats hard_cut as a one-shot build with no mix_in retries and no
    phase gate — exactly what this also needs, since there's no beat lock to
    measure or retry against (see the "hard_cut" comment inline in Pass 1).
    "soft_crossfade": True is for logging/reporting only. Pass 2 (assembly) is
    fully agnostic to hard_cut vs. this — it only reads cf_len/trim/blend/
    samples generically — so no assembly changes were needed to add this tier.
    """
    seg_a = AudioSegment.from_file(track_a["path"]).set_channels(2)
    seg_b = AudioSegment.from_file(track_b["path"]).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    effective_outro_bars = _safe_outro_bars(
        track_a.get("outro_bars", outro_bars), period_a, len(samples_a))
    cf_len = int(round(cf_bars * 4 * period_a))
    outro_target = len(samples_a) - effective_outro_bars * 4 * period_a
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    # Clamp so the forward-reading crossfade zone below always fits — unlike
    # the hard-cut's outro clamp (which reads BACKWARD from outro_sample for
    # the echo tail), this reads FORWARD, so it needs the same "- cf_len"
    # headroom build_one_transition's own outro clamp uses.
    outro_sample = max(0, min(outro_sample, len(samples_a) - cf_len))

    cue = find_cue_point(seg_b)
    b_full = samples_b[cue:]

    za = samples_a[outro_sample: outro_sample + cf_len]
    zb = b_full[:cf_len]
    n = min(len(za), len(zb))
    za, zb = za[:n], zb[:n]

    diff_pct = abs(bpm_a - bpm_b) / bpm_a * 100
    tag = f"{track_a['name']}_into_{track_b['name']}"
    print(f"    [soft-crossfade] {diff_pct:.1f}% gap — too far to bridge cleanly; "
          f"crossfading at native tempo, no forced stretch")

    if USE_EQ_BLEND:
        blend = _eq_blend(za, zb, n, sr)
    else:
        blend = np.clip(
            za * _equal_power(n, fade_in=False)[:, np.newaxis] +
            zb * _equal_power(n, fade_in=True)[:, np.newaxis],
            -1.0, 1.0,
        )
    b_full = b_full[n:]

    return {
        "tag": tag, "bpm_a": bpm_a, "bpm_b": bpm_b, "phase_err_ms": None,
        "shipped_phase_err_ms": None, "onset_ok": True,
        "samples_a": samples_a, "samples_b_s": samples_b, "outro_sample": outro_sample,
        "cf_len": n, "trim": cue, "blend": blend, "b_full": b_full, "sr": sr,
        "period_a": period_a, "cue_b": int(cue), "stretch_ratio": 1.0,
        "anchor_b_s": float(anchor_a),  # unused here; kept for key compat
        "bridged": False, "native_period_a": period_a, "native_period_b": period_b,
        "hard_cut": True, "soft_crossfade": True,
    }


def build_one_transition(track_a, track_b, out_dir, cf_bars, outro_bars, max_bpm_diff_pct=8.0):
    """Beat-align A→B, measure phase error, return metrics + audio arrays."""
    grid_a = get_or_analyze(track_a["path"], hint_bpm=track_a["hint"])
    grid_b = get_or_analyze(track_b["path"], hint_bpm=track_b["hint"])

    bpm_a, bpm_b = grid_a["bpm"], grid_b["bpm"]
    period_a = float(grid_a["beat_period_samples"])
    period_b = float(grid_b["beat_period_samples"])
    anchor_a = float(grid_a["beat_anchor_sample"])
    anchor_b = float(grid_b["beat_anchor_sample"])

    # If neither detector could confidently measure ONE of these tracks, its
    # bpm/period is just the curator's unvalidated guess standing in for a
    # real measurement — beat-matching against it is a coin flip, not a real
    # alignment, regardless of what any phase-error number says afterward
    # (confirmed live: this exact signature let one transition APPEAR to pass
    # the narrow single-point phase gate while still sounding wrong end to
    # end). Skip straight to a hard cut — no wasted mix_in retries against
    # data that was never trustworthy to begin with.
    if grid_a.get("low_confidence") or grid_b.get("low_confidence"):
        low = track_a["name"] if grid_a.get("low_confidence") else track_b["name"]
        print(f"    [low-confidence] {low}'s tempo couldn't be measured confidently — "
              f"skipping beat-matching, going straight to a hard cut")
        return _build_hard_cut_transition(track_a, track_b, out_dir, outro_bars,
                                           bpm_a, bpm_b, period_a, period_b, anchor_a)

    # Octave correction — try B relative to A first (the common case: A is a
    # normal-tempo track, B is the fast breakbeat one detected at 2x), then A
    # relative to B, before ever concluding the pair is genuinely incompatible.
    octave_fixed = _octave_match(bpm_a, bpm_b, period_b, max_bpm_diff_pct)
    if octave_fixed:
        old_bpm_b = bpm_b
        bpm_b, period_b = octave_fixed
        print(f"    [octave-fix] B: {old_bpm_b:.1f} BPM looked like a half/double-time "
              f"detection vs A's {bpm_a:.1f} BPM — treating as {bpm_b:.1f} BPM instead")
    else:
        octave_fixed = _octave_match(bpm_b, bpm_a, period_a, max_bpm_diff_pct)
        if octave_fixed:
            old_bpm_a = bpm_a
            bpm_a, period_a = octave_fixed
            print(f"    [octave-fix] A: {old_bpm_a:.1f} BPM looked like a half/double-time "
                  f"detection vs B's {bpm_b:.1f} BPM — treating as {bpm_a:.1f} BPM instead")

    diff_pct = abs(bpm_a - bpm_b) / bpm_a * 100
    if diff_pct > MAX_BRIDGE_DIFF_PCT:
        return _build_hard_cut_transition(track_a, track_b, out_dir, outro_bars,
                                           bpm_a, bpm_b, period_a, period_b, anchor_a)
    if diff_pct > SOFT_CROSSFADE_THRESHOLD_PCT:
        return _build_soft_crossfade_transition(track_a, track_b, out_dir, outro_bars,
                                                 cf_bars, bpm_a, bpm_b, period_a, period_b,
                                                 anchor_a)
    bridged = diff_pct > max_bpm_diff_pct

    seg_a = AudioSegment.from_file(track_a["path"]).set_channels(2)
    seg_b = AudioSegment.from_file(track_b["path"]).set_channels(2)
    samples_a, sr = _seg_to_f32(seg_a)
    samples_b, _  = _seg_to_f32(seg_b)

    native_period_a = period_a
    native_period_b = period_b

    if bridged:
        # Meet in the middle: pre-stretch A's whole track to the midpoint tempo
        # BEFORE any blend logic runs. Everything below operates purely in terms
        # of samples_a/period_a/anchor_a as an abstract coordinate system, so this
        # is the only change needed here — the rest of this function, and every
        # downstream body/ramp/capping calculation in build_full_set, continues
        # to work completely unchanged, now just centered on the midpoint tempo
        # instead of A's raw native tempo.
        mid_bpm    = (bpm_a + bpm_b) / 2.0
        mid_period = sr * 60.0 / mid_bpm
        ratio_a    = mid_period / period_a
        if abs(ratio_a - 1.0) > 0.0001:
            samples_a = _time_stretch_samples(samples_a, sr, ratio_a)
        anchor_a = anchor_a * ratio_a
        period_a = mid_period
        print(f"    [bridge] {diff_pct:.1f}% gap — meeting at {mid_bpm:.1f} BPM "
              f"({bpm_a:.1f}→{mid_bpm:.1f} / {bpm_b:.1f}→{mid_bpm:.1f})")

    cue = find_cue_point(seg_b)
    if cue > anchor_b:
        cue = 0
    samples_b  = samples_b[cue:]
    anchor_b  -= cue

    ratio = period_a / period_b
    samples_b_s = _time_stretch_samples(samples_b, sr, ratio) if abs(ratio - 1.0) > 0.0001 else samples_b.copy()
    anchor_b_s  = anchor_b * ratio

    # _safe_outro_bars() already exists specifically for this failure mode (a
    # track shorter than the OUTRO_BARS window — see its own docstring, the
    # "Beatles - Come Together" incident) but was only ever wired into the
    # hard-cut path. The normal blend path here used the raw, unclamped bars
    # count — so for any track where OUTRO_BARS(90) worth of beats exceeds
    # ~half the track (very common for a ~3 min song at ~100-125 BPM),
    # outro_target goes NEGATIVE and clamps to outro_sample=0 a few lines
    # down: the ENTIRE track becomes "outro," there's no solo body left at
    # all, and the blend starts at sample 0. Confirmed live 2026-08-19:
    # Purple Disco Machine - Hypnotized (195.7s, 90-bar window ≈ 200s)
    # produced exactly this — a 35.6s blend starting at t=0 with zero body,
    # which is also why a voice intro had nowhere to fit.
    effective_outro_bars = _safe_outro_bars(
        track_a.get("outro_bars", outro_bars), period_a, len(samples_a))
    outro_target = len(samples_a) - effective_outro_bars * 4 * period_a
    cf_len       = int(round(cf_bars * 4 * period_a))
    outro_sample = int(round(snap_to_beat(outro_target, anchor_a, period_a)))
    # Clamp: if track is shorter than outro_bars allows, start blend at the beginning.
    # Negative outro_sample causes numpy to wrap the slice → empty za → n=0 crash.
    outro_sample = max(0, min(outro_sample, len(samples_a) - cf_len))

    mix_in_samples = int(round(track_b.get("mix_in_bars", 16) * 4 * period_a))
    trim = _beat_this_phase_trim(
        samples_a, samples_b_s, sr,
        outro_sample, anchor_b_s + mix_in_samples, period_a, cf_bars,
    )
    trim = max(0, min(trim, len(samples_b_s) - sr))

    # Best of ±1-beat offsets — combined score: beat CV + penalty for phase drift.
    # CV alone picks the most rhythmically even blend; phase penalty breaks ties in
    # favour of lower BPM drift so the beats stay locked across the full crossfade.
    def _phase_signed_from_beats(beats_arr):
        """Returns SIGNED phase drift (ms): positive = second half late (B too slow)."""
        beats_arr = np.array(beats_arr, dtype=float)
        if len(beats_arr) < 6:
            return 0.0
        n = len(beats_arr)
        i = np.arange(n, dtype=float)
        coeffs, _, _, _ = np.linalg.lstsq(
            np.column_stack([np.ones(n), i]), beats_arr, rcond=None
        )
        anchor_fit, period_fit = coeffs
        residuals = beats_arr - (anchor_fit + i * period_fit)
        mid = n // 2
        err = float(np.mean(residuals[mid:])) - float(np.mean(residuals[:mid]))
        while err >  period_fit / 2: err -= period_fit
        while err < -period_fit / 2: err += period_fit
        return err * 1000.0

    best = {"score": 1e9, "cv": 1e9, "phase_ms": 999.0, "signed_phase_ms": 0.0}
    for offset in range(-1, 3):
        t  = max(0, min(int(round(trim + offset * period_a)), len(samples_b_s) - sr))
        b  = samples_b_s[t:]
        za = samples_a[outro_sample: outro_sample + cf_len]
        zb = b[:cf_len]
        n  = min(len(za), len(zb))
        za, zb = za[:n], zb[:n]
        blend = np.clip(
            za * _equal_power(n, fade_in=False)[:, np.newaxis] +
            zb * _equal_power(n, fade_in=True)[:, np.newaxis],
            -1.0, 1.0,
        )
        tmp = os.path.join(tempfile.gettempdir(), f"_sb_cand_{offset}.mp3")
        _f32_to_seg(blend, sr).export(tmp, format="mp3", bitrate="192k")
        try:
            from beat_this.inference import File2Beats
            beats, _ = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)(tmp)
            ibi = np.diff(beats) * 1000
            cv  = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 1 else 1.0
            signed_ms = _phase_signed_from_beats(beats)
            phase_ms  = abs(signed_ms)
        except Exception:
            cv, phase_ms, signed_ms = 1.0, 999.0, 0.0
        # 20ms phase error costs 0.3 CV points — keeps CV dominant but breaks ties
        score = cv + 0.3 * min(phase_ms, 40.0) / 20.0
        print(f"      offset {offset:+d}: CV={cv:.4f} phase={phase_ms:.1f}ms score={score:.4f}")
        if score < best["score"]:
            best = {"score": score, "cv": cv, "phase_ms": phase_ms,
                    "signed_phase_ms": signed_ms,
                    "blend": blend, "b": b, "n": n, "trim": t}

    # ── Ratio drift correction ───────────────────────────────────────────────
    # If the best blend still has residual BPM drift > 3ms, recompute the stretch
    # ratio to cancel it. Cause: beat detector period measurement is accurate to
    # ~0.02-0.1 BPM; a 0.03 BPM mismatch drifts ~7ms over a 31s blend.
    #
    # Math: measured drift D ms over T seconds with n beats means B's effective
    # period is period_a + δ where δ = D/1000 * sr * period_a / cf_len (samples).
    # Corrected ratio: ratio_new = ratio * period_a / (period_a + δ).
    # Trim rescales proportionally since beat positions scale with ratio.
    PHASE_CORR_THRESHOLD_MS = 3.0
    if best["n"] > 0 and best["phase_ms"] > PHASE_CORR_THRESHOLD_MS and abs(ratio - 1.0) < 0.10:
        err_s = best["signed_phase_ms"]
        n_beats = best["n"] / period_a
        delta   = (err_s / 1000.0) * sr * period_a / best["n"]  # samples, signed
        ratio_c = ratio * period_a / (period_a + delta)
        if 0.90 < ratio_c < 1.10:  # sanity: stay within ±10%
            b_s_c = (_time_stretch_samples(samples_b, sr, ratio_c)
                     if abs(ratio_c - 1.0) > 0.0001 else samples_b.copy())
            trim_c = max(0, min(int(round(best["trim"] * ratio_c / ratio)),
                                len(b_s_c) - sr))
            za = samples_a[outro_sample: outro_sample + cf_len]
            b_c = b_s_c[trim_c:]
            zb  = b_c[:cf_len]
            n_c = min(len(za), len(zb))
            blend_c = np.clip(
                za[:n_c] * _equal_power(n_c, fade_in=False)[:, np.newaxis] +
                zb[:n_c] * _equal_power(n_c, fade_in=True)[:, np.newaxis],
                -1.0, 1.0,
            )
            bpm_a_eff = sr * 60 / period_a
            bpm_corr  = sr * 60 / (period_a / ratio_c * ratio_c)  # = bpm_a_eff (target)
            print(f"    [drift-corr] {err_s:+.1f}ms drift → ratio {ratio:.6f}→{ratio_c:.6f} "
                  f"({(ratio_c/ratio - 1)*100:+.4f}%), expected drift ≈0ms")
            best["blend"] = blend_c
            best["b"]     = b_c
            best["n"]     = n_c
            best["trim"]  = trim_c

    # ── EQ blend (v2) ────────────────────────────────────────────────────────
    # Phase measurement (below) MUST use the equal-power blend — the bass sigmoid
    # swap creates a spectral discontinuity at p=0.5 that beat_this mistakes for a
    # phase error (observed: 6ms true error → 61ms measured on EQ blend).
    # So: keep equal-power for the BLEND.mp3 / phase gate; swap in EQ blend as the
    # "blend" value that goes into the final mix assembly.
    measure_blend = best["blend"].copy()   # always equal-power
    shipped_phase_err_ms = None
    if USE_EQ_BLEND:
        _za = samples_a[outro_sample : outro_sample + best["n"]]
        _zb = best["b"][:best["n"]]
        best["blend"] = _eq_blend(_za, _zb, best["n"], sr)

        # The equal-power measurement above is blind to a real failure mode:
        # it can't see anything the bass-swap sigmoid itself introduces or
        # reveals, since it never touches the actual shipped EQ-blend audio.
        # But measuring the shipped EQ-blend directly has its own documented
        # problem — the bass swap's spectral discontinuity at p=0.5 fools
        # beat_this into reporting a large phase error that isn't really
        # there (confirmed: a 6ms true error measured as 61ms). Splitting
        # out just the bass band and re-summing mid+high gives a signal
        # that IS the real shipped audio's rhythmic content, but without
        # the one band that confuses the detector — so it catches a genuine
        # mid/high beat-alignment problem in the ACTUAL shipped mix without
        # reintroducing the bass-swap false-positive this design already
        # avoided once before. (Confirmed live 2026-08-19: the Corona/Real
        # McCoy transition that Louis reported as audibly clashing measured
        # a clean 0.1ms on equal-power AND 0.2ms on this shipped/no-bass
        # check — neither caught it, which is why the onset-regularity
        # check below exists as a third, independent opinion.)
        _ship_bass, _ship_mid, _ship_high = _band_split(best["blend"], sr)
        _ship_no_bass = _ship_mid + _ship_high
        _ship_path = os.path.join(out_dir, f"{track_a['name']}_into_{track_b['name']}_SHIP_NOBASS.mp3")
        os.makedirs(out_dir, exist_ok=True)
        _f32_to_seg(_ship_no_bass, sr).export(_ship_path, format="mp3", bitrate="192k")
        shipped_phase_err_ms = _phase_error_ms(_ship_path)

    onset_ok = _onset_regularity_ok(best["blend"], sr) if USE_EQ_BLEND else True

    os.makedirs(out_dir, exist_ok=True)
    tag        = f"{track_a['name']}_into_{track_b['name']}"
    blend_path = os.path.join(out_dir, f"{tag}_BLEND.mp3")
    _f32_to_seg(measure_blend, sr).export(blend_path, format="mp3", bitrate="192k")

    return {
        "tag":          tag,
        "bpm_a":        sr * 60.0 / period_a,   # effective blend-native BPM (= mid_bpm if bridged)
        "bpm_b":        bpm_b,
        "phase_err_ms": _phase_error_ms(blend_path),
        "shipped_phase_err_ms": shipped_phase_err_ms,
        "onset_ok": onset_ok,
        "samples_a":    samples_a,
        "samples_b_s":  samples_b_s,
        "outro_sample": outro_sample,
        "cf_len":       best["n"],
        "trim":         best["trim"],
        "blend":        best["blend"],
        "b_full":       best["b"],
        "sr":           sr,
        "period_a":     period_a,
        "cue_b":        int(cue),
        "stretch_ratio": float(ratio),
        "anchor_b_s":   float(anchor_b_s),
        "bridged":          bridged,
        "native_period_a":  native_period_a,
        "native_period_b":  native_period_b,
    }


# ── DJ voice-intro ducking ──────────────────────────────────────────────────
# Each track dict in brain.TRACKS may carry an optional "voice_path" — an
# mp3 of DJ Kyoko's spoken intro for that track (Louis's cloned voice via
# ElevenLabs, generated in webapp/job_runner.py). When present, it's ducked
# under and mixed into that SAME track's own body audio, near the start of
# its playback — i.e. over its own quiet musical intro, exactly like a real
# radio DJ talking as the next song fades in. This never touches blend-zone
# audio or timeline length (pure in-place gain + overlay on already-finalized
# body samples), so it cannot introduce a repeat/skip/gap and cannot regress
# the phase-error or amplitude-continuity quality gates.

VOICE_DUCK_LEAD_IN_SEC  = 3.0   # must stay >= the 2s window the amplitude-
                                 # continuity check uses at blend_end (see
                                 # below) — for every track except the first,
                                 # body sample 0 IS the previous transition's
                                 # blend_end, so ducking any earlier would
                                 # corrupt the exact RMS window that check
                                 # measures. Ducking only ever starts safely
                                 # *after* that window has already passed.
VOICE_DUCK_FADE_SEC     = 1.2   # gain fade down/up around the voice-over
VOICE_DUCK_TAIL_PAD_SEC = 1.0   # quiet buffer after fade-up before we allow
                                 # anything else (BPM ramps, micro-crossfade)
                                 # in that same body to also live there
VOICE_DUCK_LEVEL        = 0.30  # duck the track's own audio to ~30% under
                                 # the voice-over (radio DJ ducking range)
VOICE_DUCK_MAX_FRACTION = 0.7   # extra safety margin: never let the duck
                                 # window extend past 70% of the body, so it
                                 # never reaches into a tail-side BPM ramp or
                                 # the final 5ms body→blend micro-crossfade


def _load_voice_audio(path, sr):
    """Decode a DJ-intro TTS mp3 to float32 stereo samples at the mix's
    sample rate. Best-effort: returns None (never raises) on any failure —
    a missing/corrupt voice-over file must never break the mix build."""
    if not path:
        return None
    try:
        seg = AudioSegment.from_file(path).set_channels(2).set_frame_rate(sr)
        samples, _ = _seg_to_f32(seg)
        return samples
    except Exception as e:  # noqa: BLE001 — decorative feature, never fail the build over it
        print(f"    (voice intro audio failed to load: {type(e).__name__}: {e})")
        return None


def _duck_and_overlay_voice(body, sr, voice_samples):
    """Best-effort: duck `body`'s own gain down, mix `voice_samples` (DJ
    Kyoko's spoken intro for this exact track) in at natural speaking volume,
    then fade the music back up to full — all within the track's own BODY
    playback, starting VOICE_DUCK_LEAD_IN_SEC into it. Returns `body`
    unmodified (same length, same array) if there's no voice audio or not
    enough room to place it safely. Never raises, never changes body length.
    """
    if voice_samples is None or len(voice_samples) == 0:
        return body
    fade_n  = int(VOICE_DUCK_FADE_SEC * sr)
    lead_n  = int(VOICE_DUCK_LEAD_IN_SEC * sr)
    tail_n  = int(VOICE_DUCK_TAIL_PAD_SEC * sr)
    voice_n = len(voice_samples)
    needed  = lead_n + fade_n + voice_n + fade_n + tail_n
    if needed >= len(body) or needed > VOICE_DUCK_MAX_FRACTION * len(body):
        print(f"    (voice intro skipped — body too short for it: "
              f"{len(body)/sr:.0f}s available, {needed/sr:.0f}s needed)")
        return body

    out = body.copy()
    voice = voice_samples.astype(np.float32)
    if voice.ndim == 1:
        voice = np.repeat(voice[:, np.newaxis], out.shape[1], axis=1)

    down_start = lead_n
    down = np.linspace(1.0, VOICE_DUCK_LEVEL, fade_n, dtype=np.float32)[:, np.newaxis]
    out[down_start:down_start + fade_n] *= down

    hold_start = down_start + fade_n
    hold_end   = hold_start + voice_n
    out[hold_start:hold_end] *= VOICE_DUCK_LEVEL
    out[hold_start:hold_end] = np.clip(out[hold_start:hold_end] + voice[:hold_end - hold_start], -1.0, 1.0)

    up_start = hold_end
    up = np.linspace(VOICE_DUCK_LEVEL, 1.0, fade_n, dtype=np.float32)[:, np.newaxis]
    out[up_start:up_start + fade_n] *= up

    print(f"    [voice intro] ducked {voice_n/sr:.1f}s of DJ Kyoko over this track's intro")
    return out


def _voice_samples_for(track, sr):
    return _load_voice_audio(track.get("voice_path"), sr)


# ── Full mix assembly ─────────────────────────────────────────────────────────

def build_full_set(brain):
    """
    Build a complete DJ set from a brain module.

    brain must expose: SET_NAME, SET_NOTES, TRACKS, CF_BARS, OUTRO_BARS, SNIPPET_SEC
    """
    tracks      = brain.TRACKS
    set_name    = brain.SET_NAME
    set_notes   = brain.SET_NOTES
    cf_bars       = getattr(brain, "CF_BARS",       8)
    outro_bars    = getattr(brain, "OUTRO_BARS",    16)
    snippet_sec   = getattr(brain, "SNIPPET_SEC",   6)
    skip_snippets = getattr(brain, "SKIP_SNIPPETS", False)

    out_dir      = os.path.join("output", set_name)
    blend_dir    = os.path.join("output", "transitions", set_name)
    os.makedirs(out_dir,   exist_ok=True)
    os.makedirs(blend_dir, exist_ok=True)

    print(f"\n{'═'*65}")
    print(f"  Building: {set_name.upper().replace('_',' ')}")
    print(f"  {len(tracks)} tracks  |  CF={cf_bars}bars  OUTRO={outro_bars}bars")
    print(f"{'═'*65}\n")

    grid_0 = get_or_analyze(tracks[0]["path"], hint_bpm=tracks[0]["hint"])
    print(f"  [01] {tracks[0]['label']}  —  {grid_0['bpm']:.2f} BPM")

    # ── Pass 1: build all transitions ─────────────────────────────────────────
    transitions = []
    for i in range(1, len(tracks)):
        prev, curr = tracks[i - 1], tracks[i]
        print(f"\n  [{i+1:02d}] {curr['label']}")
        print(f"       {prev['name']} → {curr['name']}...")

        _default_mix_in = curr.get("mix_in_bars", 16)
        _seen, MIX_IN_ATTEMPTS = set(), []
        for _v in [_default_mix_in, 16, 32, 8, 48, 0, 24]:
            if _v not in _seen:
                _seen.add(_v)
                MIX_IN_ATTEMPTS.append(_v)
        tr, phase_ms, shipped_ms, onset_ok = None, None, None, True
        for mix_in in MIX_IN_ATTEMPTS:
            tr = build_one_transition(
                prev, dict(curr, mix_in_bars=mix_in),
                blend_dir, cf_bars, outro_bars,
                max_bpm_diff_pct=getattr(brain, "MAX_BPM_DIFF_PCT", 8.0),
            )
            if tr.get("hard_cut"):
                # No beat-matching attempted — mix_in_bars is meaningless here,
                # retrying with a different value changes nothing. One shot only.
                break
            phase_ms = tr["phase_err_ms"]
            shipped_ms = tr["shipped_phase_err_ms"]
            onset_ok = tr["onset_ok"]
            # Three independent checks, all must pass. Beat-matching correctness
            # is the top priority for this project (see CLAUDE.md) — a single
            # metric passing isn't good enough on its own. Confirmed live
            # 2026-08-19: a Corona/Real McCoy transition measured a clean 0.1ms
            # equal-power AND 0.2ms shipped/no-bass — both passed — while Louis
            # reported it as audibly clashing beats. The onset-regularity check
            # is what actually catches that case (see _onset_regularity_ok).
            passed = (phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS and
                      (shipped_ms is None or shipped_ms < PHASE_THRESHOLD_MS) and
                      onset_ok)
            if passed:
                if mix_in != curr.get("mix_in_bars", 16):
                    print(f"       Retried with mix_in_bars={mix_in}")
                break
            ship_note = f", shipped={shipped_ms}ms" if shipped_ms is not None else ""
            onset_note = "" if onset_ok else ", onset-irregular"
            print(f"       mix_in={mix_in}: {phase_ms}ms{ship_note}{onset_note} — retrying...")

        if tr.get("hard_cut"):
            if tr.get("soft_crossfade"):
                print(f"       Soft crossfade (too far to beat-match, close enough to blend) ≈")
            else:
                print(f"       Hard cut (tempos too far apart to blend) ✂")
        else:
            gate_passed = (phase_ms is not None and phase_ms < PHASE_THRESHOLD_MS and
                           (shipped_ms is None or shipped_ms < PHASE_THRESHOLD_MS) and
                           onset_ok)
            sym = "✓" if gate_passed else "✗"
            ship_note = f"  (shipped: {shipped_ms}ms)" if shipped_ms is not None else ""
            onset_note = "  (onset-irregular)" if not onset_ok else ""
            print(f"       Phase error: {phase_ms}ms{ship_note}{onset_note}  {sym}")

            if not gate_passed:
                # All mix_in_bars positions failed to align, despite BPMs looking
                # numerically compatible — this means the underlying tempo/beat-
                # grid data itself is unreliable for this pair (e.g. a low-
                # confidence beat detection silently fell back to the curator's
                # raw BPM guess instead of a real measurement — a giveaway is an
                # exactly-round "BPM=122.0000" in the log above, four zero
                # decimals, vs. a real measurement's usual fractional noise).
                # No mix_in retry can fix a wrong tempo estimate, and previously
                # this hard-crashed via sys.exit(1) — which is NOT caught by
                # run_job()'s `except Exception` (SystemExit isn't an Exception
                # subclass), so the job hung at "mixing" forever with no error
                # ever surfacing. Confirmed live 2026-08-18. Fall back to a hard
                # cut instead — same graceful-degradation technique already
                # built for BPM-incompatible pairs, and it doesn't depend on
                # phase/tempo alignment being trustworthy at all.
                print(f"\n  !! Phase alignment failed after {len(MIX_IN_ATTEMPTS)} attempts "
                      f"({prev['name']}→{curr['name']}, best={phase_ms}ms) — the tempo/beat "
                      f"data for this pair isn't trustworthy enough to blend. Falling back "
                      f"to a hard cut instead of forcing an unreliable beat-matched blend.")
                grid_a = get_or_analyze(prev["path"], hint_bpm=prev["hint"])
                tr = _build_hard_cut_transition(
                    prev, curr, blend_dir, outro_bars,
                    grid_a["bpm"], tr["bpm_b"],
                    float(grid_a["beat_period_samples"]), tr["native_period_b"],
                    float(grid_a["beat_anchor_sample"]),
                )
                phase_ms = None

        transitions.append({"tr": tr, "prev": prev, "curr": curr, "phase_ms": phase_ms})

    # ── Pass 2: assemble mix ──────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("  Assembling full mix...")

    _body_cap_range = getattr(brain, "MAX_BODY_SEC_RANGE", None)
    if _body_cap_range:
        def _next_max_body_sec():
            return random.uniform(_body_cap_range[0], _body_cap_range[1])
    else:
        _fixed_body_cap = int(getattr(brain, "MAX_BODY_SEC", 180))
        def _next_max_body_sec():
            return _fixed_body_cap

    mix_audio, mix_len, snippet_clips = None, 0, []
    _, sr = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))

    def _reblend(a_audio, b_audio, cf_len):
        """EQ-style crossfade for capped-body reblends (v2). Falls back to equal-power when USE_EQ_BLEND=False."""
        n = min(len(a_audio), len(b_audio), cf_len)
        if USE_EQ_BLEND:
            return _eq_blend(a_audio, b_audio, n, sr)
        return np.clip(
            a_audio[:n] * _equal_power(n, fade_in=False)[:, np.newaxis] +
            b_audio[:n] * _equal_power(n, fade_in=True)[:, np.newaxis],
            -1.0, 1.0,
        )

    for idx in range(len(tracks)):
        if idx == 0:
            tr0    = transitions[0]["tr"]
            raw, _ = _seg_to_f32(AudioSegment.from_file(tracks[0]["path"]).set_channels(2))

            if tr0.get("bridged"):
                # tr0["outro_sample"]/["period_a"] are in STRETCHED (mid-tempo)
                # coordinates (build_one_transition pre-stretches the whole of A
                # for a bridged transition) but `raw` here is native, unstretched
                # audio — convert back to native coordinates via the same uniform
                # ratio used to produce the stretch, matching how anchor_b_s/cue_b
                # already convert between native and stretched B elsewhere in this
                # file. Never cap a bridged opening body — capping would require
                # reblending native-tempo A against a mid-tempo B (BPM mismatch
                # baked into the reblend itself), which needs its own bar-phase-
                # matching fix like the capped-mismatch case below; simpler and
                # safe to just not cap this rare combination.
                bridge_ratio_a = tr0["period_a"] / tr0["native_period_a"]
                outro_native   = int(round(tr0["outro_sample"] / bridge_ratio_a))
                body   = raw[:outro_native].copy()
                capped = False
                if abs(bridge_ratio_a - 1.0) > RAMP_THRESHOLD:
                    bpm_from = sr * 60 / tr0["native_period_a"]
                    bpm_to   = sr * 60 / tr0["period_a"]
                    print(f"    [bridge-ramp-out] {tracks[0]['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM over {RAMP_BARS} bars")
                    body = _bpm_ramp(body, sr, bridge_ratio_a, tr0["native_period_a"])
                blend_audio = tr0["blend"].copy()
                # 5ms micro-crossfade: body is linear-interp-ramped raw audio, blend
                # is pyrubberband-stretched — different processing chains reaching
                # the same target tempo don't produce identical sample values at the
                # exact splice point. Same fix as the idx>0 body→blend splice below.
                micro_n = int(0.005 * sr)
                if micro_n > 0 and len(body) >= micro_n and len(blend_audio) >= micro_n:
                    t = np.linspace(0.0, 1.0, micro_n)[:, np.newaxis]
                    body[-micro_n:] = body[-micro_n:] * (1.0 - t) + blend_audio[:micro_n] * t
                    blend_audio = blend_audio[micro_n:]
            else:
                # Cap body at 3 min; if capped, recompute blend from that point
                body_end = min(tr0["outro_sample"], int(_next_max_body_sec() * sr))
                body = raw[:body_end]
                capped = body_end < tr0["outro_sample"]
                blend_audio = _reblend(raw[body_end:], tr0["b_full"], tr0["cf_len"]) if capped else tr0["blend"]

            body = _duck_and_overlay_voice(body, sr, _voice_samples_for(tracks[0], sr))

            mix_audio = body
            mix_len   = len(body)
            blend_start = mix_len
            mix_audio = np.concatenate([mix_audio, blend_audio], axis=0)
            mix_len  += len(blend_audio)

            blend_end = blend_start + len(blend_audio)
            print(f"  [body] {tracks[0]['name']}: {len(body)/sr:.0f}s{' (capped)' if capped else ''}")
            snippet_clips.append({
                "idx":         1,
                "name_a":      transitions[0]["prev"]["name"],
                "name_b":      transitions[0]["curr"]["name"],
                "label_b":     transitions[0]["curr"].get("label", transitions[0]["curr"]["name"]),
                "start":       max(0, blend_start - snippet_sec * sr),
                "end":         blend_end + snippet_sec * sr,
                "blend_start": blend_start,
                "blend_end":   blend_end,
            })

        elif idx < len(transitions):
            tr_prev = transitions[idx - 1]["tr"]
            tr_next = transitions[idx]["tr"]

            # Body: stretched audio at tr_prev["period_a"] BPM — continuous from blend-in.
            # (Switching to native BPM here causes the audible BPM jump the user hears.)
            b_s = tr_prev["samples_b_s"]
            # outro_stretched: position in b_s (which starts at cue_b into native B)
            # corresponding to outro_sample in the full native track.
            # Wrong formula: outro_sample × len(b_s)/len(native_full)  -- ignores cue offset
            # Right formula:  (outro_sample - cue_b) × stretch_ratio
            cue_b   = tr_prev.get("cue_b", 0)
            ratio_b = tr_prev.get("stretch_ratio", 1.0)
            outro_stretched = int((tr_next["outro_sample"] - cue_b) * ratio_b)

            body_start = tr_prev["trim"] + tr_prev["cf_len"]

            # Cap body at 3 min, snapped to bar boundary in playing (stretched) BPM.
            # Snap backward from outro_stretched in whole-bar steps so body_end lands
            # on the same bar phase as outro_stretched — matching the phase that B's
            # trim was aligned to. Forward-snap from body_start lands on a different
            # bar phase when outro_stretched isn't at beat 0 → B sounds off by a beat.
            bar_samples = 4.0 * tr_prev["period_a"]
            max_body_samples = int(_next_max_body_sec() * sr)
            raw_body_dur = outro_stretched - body_start
            if raw_body_dur > max_body_samples:
                max_end = body_start + max_body_samples
                k = math.ceil((outro_stretched - max_end) / bar_samples)
                body_end = int(round(outro_stretched - k * bar_samples))
                while body_end > max_end:
                    k += 1
                    body_end = int(round(outro_stretched - k * bar_samples))
                capped = True
            else:
                body_end = outro_stretched
                capped = False

            b_body = b_s[body_start : body_end].copy()
            body_dur_s = len(b_body) / sr
            print(f"  [body] {transitions[idx-1]['curr']['name']}: {body_dur_s:.0f}s{' (capped)' if capped else ''}")

            # Use pre-computed blend (both sides already beat-aligned at outgoing native BPM).
            # If body was capped and BPMs differ, the body runs at the PREVIOUS A's period while
            # b_full runs at the NEXT A's (native) period → beats drift during the crossfade.
            # Fix: ramp body BPM → native, snap body_end to a native bar boundary, then reblend
            # using samples_a (native A audio) so both sides of _reblend are at the same BPM.
            if body_end < outro_stretched:
                body_period   = tr_prev["period_a"]
                native_period = tr_next["period_a"]
                # Hard cuts (and soft-crossfades, which reuse the hard_cut
                # contract) never beat-match, so there is nothing on either
                # side for this body to ramp toward. tr_prev["period_a"] also
                # isn't even this body's own tempo when tr_prev is a hard
                # cut — hard cuts never stretch B, so the body plays at its
                # own native BPM, not the previous track's period_a. Ramping
                # toward it was both pointless and wrong (confirmed live
                # 2026-09-04: cross-sr-rate hard-cut set computed a bogus
                # 132.8 BPM ramp target — no track in the set was near that
                # tempo — traced to reusing a period_a sample count computed
                # at one track's native sample rate as if it were in the
                # mix's working sample rate). Skip ramping entirely whenever
                # either adjacent transition is a hard cut/soft-crossfade.
                do_ramp = (abs(body_period / native_period - 1.0) > 0.001
                           and not tr_prev.get("hard_cut")
                           and not tr_next.get("hard_cut"))
                if do_ramp:
                    # BPM mismatch in capped reblend — fix it.
                    cue_b_prev      = tr_prev["cue_b"]
                    ratio_prev      = tr_prev["stretch_ratio"]
                    anchor_b_s_prev = tr_prev.get("anchor_b_s", 0.0)

                    # Convert body_end to native track coordinates.
                    native_body_end  = cue_b_prev + body_end / ratio_prev

                    # Snap backward from outro_sample in whole-bar steps so native_bar_end
                    # has the same bar phase as outro_sample — matching B's trim alignment.
                    native_outro = tr_next["outro_sample"]
                    native_bar_samples = 4.0 * native_period
                    k_n = math.ceil((native_outro - native_body_end) / native_bar_samples)
                    native_bar_end = int(round(native_outro - k_n * native_bar_samples))
                    while native_bar_end > native_body_end:
                        k_n += 1
                        native_bar_end = int(round(native_outro - k_n * native_bar_samples))

                    # Re-slice body to match the native bar boundary.
                    body_end_fix = max(body_start, int(round((native_bar_end - cue_b_prev) * ratio_prev)))
                    b_body = b_s[body_start:body_end_fix].copy()

                    # Ramp body BPM → native BPM over the last RAMP_BARS bars.
                    ramp_ratio = native_period / body_period
                    bpm_from   = sr * 60 / body_period
                    bpm_to     = sr * 60 / native_period
                    print(f"    [capped-ramp] {transitions[idx-1]['curr']['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM")
                    b_body = _bpm_ramp(b_body, sr, ramp_ratio, body_period)

                    # Both sides now at native BPM — beats stay aligned through the whole blend.
                    blend_audio = _reblend(
                        tr_next["samples_a"][native_bar_end:],
                        tr_next["b_full"],
                        tr_next["cf_len"],
                    )
                else:
                    blend_audio = _reblend(b_s[body_end:], tr_next["b_full"], tr_next["cf_len"])
            else:
                blend_audio = tr_next["blend"].copy()

            # BPM ramp: gradually nudge body BPM → blend native BPM over the last RAMP_BARS
            # bars. Applied to ALL non-capped bodies (RAMP_THRESHOLD=0.0). When BPMs match
            # exactly (ratio=1.0), the inner guard in _bpm_ramp skips all pyrubberband calls.
            # Capped bodies with BPM mismatch are handled above; same-BPM capped skip ramp.
            # Same hard-cut/soft-crossfade guard as the capped-ramp branch above —
            # no beat-matching on either side means no target tempo to ramp toward.
            if not capped and not tr_prev.get("hard_cut") and not tr_next.get("hard_cut"):
                ramp_ratio = tr_next["period_a"] / tr_prev["period_a"]
                if abs(ramp_ratio - 1.0) > RAMP_THRESHOLD:
                    bpm_from = sr * 60 / tr_prev["period_a"]
                    bpm_to   = sr * 60 / tr_next["period_a"]
                    print(f"    [ramp] {transitions[idx-1]['curr']['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM over {RAMP_BARS} bars")
                    b_body = _bpm_ramp(b_body, sr, ramp_ratio, tr_prev["period_a"])

            # Bridged-transition ramp-IN: if the PREVIOUS transition met tempos in
            # the middle (see MAX_BRIDGE_DIFF_PCT), this body starts at that
            # midpoint and needs to settle back to its own true native tempo over
            # its first RAMP_BARS bars — the mirror of the ramp-out used to
            # approach a blend. Independent of the tail-side ramp(s) above (head
            # vs tail, disjoint regions for any real body length).
            if tr_prev.get("bridged"):
                bridge_ratio = tr_prev["period_a"] / tr_prev["native_period_b"]
                if abs(bridge_ratio - 1.0) > RAMP_THRESHOLD:
                    bpm_from = sr * 60 / tr_prev["period_a"]
                    bpm_to   = sr * 60 / tr_prev["native_period_b"]
                    print(f"    [bridge-ramp-in] {transitions[idx-1]['curr']['name']}: "
                          f"{bpm_from:.1f}→{bpm_to:.1f} BPM over {RAMP_BARS} bars")
                    b_body = _bpm_ramp_in(b_body, sr, bridge_ratio, tr_prev["native_period_b"])

            b_body = _duck_and_overlay_voice(b_body, sr, _voice_samples_for(tracks[idx], sr))

            # 5ms micro-crossfade at body→blend splice.
            # Body uses stretched audio from the PREVIOUS transition's build; blend uses native
            # audio loaded fresh in the NEXT transition's build. Different processing chains of
            # the same source → sample values don't match exactly → audible click without this.
            micro_n = int(0.005 * sr)
            if micro_n > 0 and len(b_body) >= micro_n and len(blend_audio) >= micro_n:
                t = np.linspace(0.0, 1.0, micro_n)[:, np.newaxis]
                b_body[-micro_n:] = b_body[-micro_n:] * (1.0 - t) + blend_audio[:micro_n] * t
                blend_audio = blend_audio[micro_n:]

            blend_start = mix_len + len(b_body)
            mix_audio = np.concatenate([mix_audio, b_body, blend_audio], axis=0)
            mix_len  += len(b_body) + len(blend_audio)

            blend_end = blend_start + len(blend_audio)
            snippet_clips.append({
                "idx":         idx + 1,
                "name_a":      transitions[idx]["prev"]["name"],
                "name_b":      transitions[idx]["curr"]["name"],
                "label_b":     transitions[idx]["curr"].get("label", transitions[idx]["curr"]["name"]),
                "start":       max(0, blend_start - snippet_sec * sr),
                "end":         blend_end + snippet_sec * sr,
                "blend_start": blend_start,
                "blend_end":   blend_end,
            })

        else:
            tr_prev    = transitions[-1]["tr"]
            body_start = tr_prev["trim"] + tr_prev["cf_len"]
            raw_last   = tr_prev["samples_b_s"][body_start:]

            # Cap the last track like every other body instead of always
            # playing it out to its full natural length uncapped — otherwise
            # a long final track dominates the mix's ending on its own,
            # independent of how varied the earlier bodies were.
            max_last_samples = int(_next_max_body_sec() * sr)
            if len(raw_last) > max_last_samples:
                bar_samples = 4.0 * tr_prev["period_a"]
                anchor_b_s  = tr_prev.get("anchor_b_s", 0.0)
                cap_target  = body_start + max_last_samples
                n_bars      = math.floor((cap_target - anchor_b_s) / bar_samples)
                cut_at      = int(round(anchor_b_s + n_bars * bar_samples - body_start))
                cut_at      = max(1, min(cut_at, len(raw_last)))
                last_body   = raw_last[:cut_at].copy()
                fade_n = min(int(3.0 * sr), len(last_body))
                if fade_n > 0:
                    fade = np.linspace(1.0, 0.0, fade_n)[:, np.newaxis]
                    last_body[-fade_n:] *= fade
                print(f"  [last-body] {tracks[-1]['name']}: capped to {len(last_body)/sr:.0f}s "
                      f"with fade-out (was {len(raw_last)/sr:.0f}s)")
            else:
                last_body = raw_last.copy()

            if tr_prev.get("bridged"):
                bridge_ratio = tr_prev["period_a"] / tr_prev["native_period_b"]
                if abs(bridge_ratio - 1.0) > RAMP_THRESHOLD:
                    bpm_from = sr * 60 / tr_prev["period_a"]
                    bpm_to   = sr * 60 / tr_prev["native_period_b"]
                    print(f"    [bridge-ramp-in] {tracks[-1]['name']}: {bpm_from:.1f}→{bpm_to:.1f} BPM over {RAMP_BARS} bars")
                    last_body = _bpm_ramp_in(last_body, sr, bridge_ratio, tr_prev["native_period_b"])

            last_body = _duck_and_overlay_voice(last_body, sr, _voice_samples_for(tracks[idx], sr))

            mix_audio = np.concatenate([mix_audio, last_body], axis=0)
            mix_len  += len(last_body)

    total_min = len(mix_audio) / sr / 60
    print(f"  Full mix: {total_min:.1f} min")

    # ── Amplitude continuity check at every blend boundary ────────────────────
    # 2-second window: wide enough to catch any loud transient near the seam
    # 2-second window for blend boundaries; threshold 3.0x accounts for normal
    # musical dynamics over a 2s span (narrow 300ms window needed 2.5x, but 2s
    # smooths most transients — only flag true construction gaps).
    print(f"\n  Checking blend boundaries (RMS ratio threshold 3.0x, 2s window)...")
    window = int(2.0 * sr)
    CUT_THRESHOLD = 3.0
    cut_found = False
    for clip in snippet_clips:
        bs = clip.get("blend_start", 0)
        be = clip.get("blend_end", 0)
        label = f"{clip['name_a']}→{clip['name_b']}"

        # blend-in: body ends, new track starts fading in
        if bs >= window and bs + window < len(mix_audio):
            pre  = float(np.sqrt(np.mean(_mono(mix_audio[bs - window: bs]) ** 2))) + 1e-9
            post = float(np.sqrt(np.mean(_mono(mix_audio[bs: bs + window]) ** 2))) + 1e-9
            ratio = max(pre, post) / min(pre, post)
            sym = "✓" if ratio < CUT_THRESHOLD else "✗ CUT"
            print(f"    [{clip['idx']:02d}] blend-in   {label:<32}  RMS ratio {ratio:.2f}  {sym}")
            if ratio >= CUT_THRESHOLD:
                cut_found = True

        # blend-out: outgoing track has faded, body of incoming track begins
        if be >= window and be + window < len(mix_audio):
            pre  = float(np.sqrt(np.mean(_mono(mix_audio[be - window: be]) ** 2))) + 1e-9
            post = float(np.sqrt(np.mean(_mono(mix_audio[be: be + window]) ** 2))) + 1e-9
            ratio = max(pre, post) / min(pre, post)
            sym = "✓" if ratio < CUT_THRESHOLD else "✗ CUT"
            print(f"    [{clip['idx']:02d}] blend-out  {label:<32}  RMS ratio {ratio:.2f}  {sym}")
            if ratio >= CUT_THRESHOLD:
                cut_found = True

    if cut_found:
        print("  !! WARNING: amplitude discontinuity detected — check the flagged transitions")
    else:
        print("  All blend boundaries clean ✓")

    full_path = os.path.join(out_dir, "FULL_SET.mp3")
    print(f"  Exporting FULL_SET.mp3...")
    _f32_to_seg(mix_audio, sr).export(full_path, format="mp3", bitrate="256k")
    print(f"  ✓ {full_path}")

    if skip_snippets:
        print(f"\n  Skipping transition snippets (SKIP_SNIPPETS=True)")
    else:
        print(f"\n  Exporting transition snippets...")
        for clip in snippet_clips:
            s, e = int(clip["start"]), min(int(clip["end"]), len(mix_audio))
            fname = f"{clip['idx']:02d}_{clip['name_a']}_into_{clip['name_b']}.mp3"
            _f32_to_seg(mix_audio[s:e], sr).export(
                os.path.join(out_dir, fname), format="mp3", bitrate="192k"
            )
            print(f"  ✓ {fname}  ({(e-s)/sr:.1f}s)")

    # ── Auto-generate CUE SHEET from actual blend times ──────────────────────
    def _ts(samples):
        s = int(samples / sr)
        return f"{s // 60:02d}:{s % 60:02d}"

    def _tier_note(tr):
        """
        One-line "why this transition sounds the way it does" for the cue
        sheet (2026-09-04) — reads the same tr["hard_cut"]/["bridged"]/
        ["soft_crossfade"]/["phase_err_ms"] fields set by
        build_one_transition/_build_hard_cut_transition/
        _build_soft_crossfade_transition. Read-only annotation of an
        already-built transition — does not affect how any transition is
        built.
        """
        if tr.get("hard_cut"):
            if tr.get("soft_crossfade"):
                return "soft crossfade — too far to beat-match, close enough to blend cleanly"
            return "hard cut — tempos too far apart (or beat data unreliable) to blend"
        if tr.get("bridged"):
            return "bridged beat-match — forced tempo bridge past normal tolerance"
        phase = tr.get("phase_err_ms")
        if phase is not None:
            return f"beat-matched blend — phase error {phase:.1f}ms"
        return "beat-matched blend"

    cf_dur_s = round(snippet_clips[0]["blend_end"] - snippet_clips[0]["blend_start"]) / sr if snippet_clips else 0
    first_label = tracks[0].get("label", tracks[0]["name"])
    cue_lines = [
        f"\n── CUE SHEET ──────────────────────────────────────────────────────────────────",
        f"  Each crossfade is ~{int(cf_dur_s)}s long.",
        f"",
        f"  00:00        Set starts — {first_label}",
    ]
    for clip in snippet_clips:
        bs = _ts(clip["blend_start"])
        be = _ts(clip["blend_end"])
        label = clip.get("label_b", clip["name_b"])
        n = clip["idx"]
        suffix = "  ← PEAK" if label in ("Rampa - The Touch",) else ("  ← close" if "Stimming" in label else "")
        cue_lines.append(f"  {bs}–{be}  [{n:02d}] → {label}{suffix}")
        if 0 <= n - 1 < len(transitions):
            cue_lines.append(f"               {_tier_note(transitions[n - 1]['tr'])}")

    set_end_s = int(len(mix_audio) / sr)
    cue_lines.append(f"  {set_end_s // 60:02d}:{set_end_s % 60:02d}         Set ends")
    cue_sheet = "\n".join(cue_lines)

    # Strip any existing CUE SHEET block from the brain's set_notes string
    notes_body = set_notes
    if "── CUE SHEET" in notes_body:
        notes_body = notes_body[:notes_body.index("── CUE SHEET")].rstrip()

    notes_path = os.path.join(out_dir, "SET_NOTES.txt")
    with open(notes_path, "w") as f:
        f.write(notes_body + cue_sheet + "\n")
    print(f"\n  ✓ {notes_path}")

    # Machine-readable cue points — the same blend_start/blend_end data used
    # for the human-readable cue sheet above, in seconds, for the web UI to
    # render transition markers on the seek bar (midpoint of each blend — for
    # a beat-matched crossfade that's roughly where A and B are equally
    # present; for a hard-cut/echo-out it's partway through the echo decay,
    # still a reasonable "here's the handoff" marker).
    markers_sec = [round(((c["blend_start"] + c["blend_end"]) / 2) / sr, 1) for c in snippet_clips]
    cue_points = {
        "track_starts_sec": [0.0] + markers_sec,
        "transition_markers_sec": markers_sec,
        "total_sec": round(len(mix_audio) / sr, 1),
    }
    with open(os.path.join(out_dir, "cue_points.json"), "w") as f:
        json.dump(cue_points, f)

    print(f"\n{'═'*65}")
    print(f"  SET COMPLETE: output/{set_name}/")
    print(f"{'═'*65}")
    print(f"  Transitions (threshold < {PHASE_THRESHOLD_MS}ms):")
    for t in transitions:
        if t["phase_ms"] is None:
            sym, label = "✂", "hard cut"
        else:
            sym  = "✓" if t["phase_ms"] < PHASE_THRESHOLD_MS else "✗ FAIL"
            label = f"{t['phase_ms']}ms"
        print(f"    {t['prev']['name']:<14} → {t['curr']['name']:<14}  {label}  {sym}")
    print()

    return out_dir
