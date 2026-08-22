"""
Runs one DJ Kyoko mix build to completion, reporting real, live progress.

Design: rather than threading progress callbacks through the whole mixing
engine (mixer/set_builder.py — dense, numerically delicate code, not worth
the risk of touching for UI purposes), this captures the pipeline's own
stdout in real time and both (a) republishes every line verbatim as the
live "story" log and (b) regex-parses known line shapes to update
structured progress fields. Every progress number shown to the user is
derived from something the pipeline actually printed — nothing here is
simulated or estimated on a timer.

Runs entirely inside its own OS process (see server.py), so redirecting
sys.stdout globally here is safe — it never touches any other job.
"""
import json
import os

# MUST run before numpy/torch/librosa are imported anywhere in this process
# (including transitively, below) — confirmed via live concurrent testing:
# without this, each job's numeric libraries (OpenBLAS/MKL/torch) each try
# to use EVERY core by default, so N concurrent jobs oversubscribe the
# machine N-fold and thrash each other instead of running cleanly in
# parallel — CPU usage was observed oscillating wildly (221%, then 35%,
# then 0%) instead of settling into steady utilization, and a mix that
# normally takes a few minutes took 15+ minutes and counting under load.
# multiprocessing's default "spawn" start method re-executes this whole
# module fresh in each child process, so setting these at true module level
# (not inside run_job) is what makes them apply before any BLAS/torch
# thread pool actually initializes.
#
# These env vars are inherited by subprocess.Popen/run calls too — which
# matters because the mixing engine shells out to the external `rubberband`
# CLI for time-stretching, not just in-process numpy/torch. A first attempt
# at this fix divided by 3 (assuming 3 concurrent jobs) and throttled
# rubberband too hard: on a large tempo-stretch ratio, one rubberband
# invocation was caught live still running 44+ seconds after its sibling
# job had already finished — confirmed via `ps` snapshots showing the same
# PID, same in/out temp files, growing elapsed time. Matching the divisor
# to server.py's actual MAX_CONCURRENT (2, not 3) gives each job enough
# headroom (5 threads on a 10-core machine) to avoid that starvation while
# still preventing the original full-oversubscription thrashing.
_THREADS_PER_JOB = max(1, (os.cpu_count() or 4) // 2)  # 2 == server.py's MAX_CONCURRENT
for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_var] = str(_THREADS_PER_JOB)

import queue
import random
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mixer.curate import curate_and_validate, BillingCapError, ANTHROPIC_URL
from mixer.set_builder import build_full_set
from mixer.story import generate_mix_story, generate_story_image, generate_track_intros
from mixer.voice import generate_track_intro_audio

try:
    import torch
    torch.set_num_threads(_THREADS_PER_JOB)
except ImportError:
    pass

# A single yt-dlp invocation must never be able to hang a job forever. Two
# independent caps: DOWNLOAD_IDLE_TIMEOUT_SEC catches a process that's still
# alive but has stopped producing any output at all (e.g. a stuck network
# read with no error surfaced yet); DOWNLOAD_HARD_TIMEOUT_SEC is a backstop
# for a process that keeps producing output but never actually finishes.
# Both just make one _run() attempt fail — the existing 3-attempt retry
# chain in _download_with_progress already handles a single failed attempt.
DOWNLOAD_IDLE_TIMEOUT_SEC = 90
DOWNLOAD_HARD_TIMEOUT_SEC = 600

DOWNLOAD_PCT_RE = re.compile(r"\[download\]\s+([\d.]+)% of")
TRANSITION_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+)$")
PHASE_ERR_RE = re.compile(r"Phase error:\s*([\d.]+)ms\s*(✓|✗)?")

GALLERY_URL = os.environ.get("DJBOT_GALLERY_URL", "https://djbot-gallery-production.up.railway.app")
APP_SUPPORT = Path(os.environ.get(
    "DJBOT_APP_SUPPORT",
    str(Path.home() / "Library" / "Application Support" / "DJ Kyoko"),
))
USERNAME_FILE = APP_SUPPORT / "username.txt"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "custom_mix"


class _Brain:
    def __init__(self, style_name, set_name, notes, tracks):
        self.STYLE_NAME = style_name
        self.SET_NAME = set_name
        self.SET_NOTES = notes
        self.BPM_RANGE = (60, 200)
        self.CF_BARS = 16
        self.OUTRO_BARS = 90
        self.SNIPPET_SEC = 15
        self.MAX_BPM_DIFF_PCT = 15.0
        self.MAX_BODY_SEC_RANGE = (60, 210)  # 1-3.5 min per track — real variety, not a narrow ~2min band
        self.SKIP_SNIPPETS = True  # only the full mix matters for this flow
        self.TRACKS = tracks


class _LiveLogWriter:
    """Replaces sys.stdout for the duration of a job — every real print()
    from the pipeline (curate.py, set_builder.py, this file) flows through
    here line-by-line and gets published to the shared job state."""

    def __init__(self, on_line):
        self._on_line = on_line
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._on_line(line)

    def flush(self):
        pass


class JobContext:
    """Owns one job's state dict + the publish/log/emit plumbing."""

    def __init__(self, job_id, request_text, minutes, jobs_dict):
        self.job_id = job_id
        self.jobs_dict = jobs_dict
        self.state = {
            "id": job_id,
            "request": request_text,
            "minutes": minutes,
            "status": "starting",
            "stage_label": "Starting up...",
            "created_at": time.time(),
            "started_at": time.time(),
            "tracks": [],
            "log": [],
            "percent": 0,
            "eta_seconds": None,
            "error": None,
            "error_type": None,
            "output_rel_path": None,
            "narrative": None, "mix_name": None,
            "story_image_url": None,
            "dj_image_url": None,
            "published": None,
        }
        self._eta_smoothed = None
        self._last_publish = 0.0
        self.publish(force=True)

    # ---- publishing ----------------------------------------------------
    def publish(self, force=False):
        now = time.time()
        if not force and now - self._last_publish < 0.15:
            return
        self._last_publish = now
        self._recompute_percent_and_eta()
        self.jobs_dict[self.job_id] = dict(self.state)

    def set(self, **kw):
        # Explicit state changes (status transitions, final results) must
        # never be silently dropped by the log throttle — force-publish.
        self.state.update(kw)
        self.publish(force=True)

    def log_line(self, line):
        if not line.strip():
            return
        self.state["log"].append({"t": time.time(), "msg": line})
        if len(self.state["log"]) > 400:
            self.state["log"] = self.state["log"][-400:]
        self._maybe_parse_mixing_line(line)
        self.publish()

    def error(self, message, error_type=None):
        self.state["status"] = "error"
        self.state["error"] = message
        self.state["error_type"] = error_type
        self.state["stage_label"] = "Something went wrong"
        self.publish(force=True)

    # ---- parsing ---------------------------------------------------------
    def _maybe_parse_mixing_line(self, line):
        if self.state["status"] != "mixing":
            return
        m = TRANSITION_RE.match(line)
        if m:
            idx = int(m.group(1))
            total = max(1, len(self.state["tracks"]) - 1)
            self.state["mix_progress"] = {
                "current": min(idx, total),
                "total": total,
                "label": m.group(2).strip(),
            }
            self.state["stage_label"] = f"Beat-matching {m.group(2).strip()}"

    def _recompute_percent_and_eta(self):
        status = self.state["status"]
        if status in ("starting", "curating"):
            pct = 3.0
        elif status == "downloading":
            tracks = self.state["tracks"]
            if tracks:
                pct = 8 + 32 * (sum(t["download_pct"] for t in tracks) / (100 * len(tracks)))
            else:
                pct = 8
        elif status == "mixing":
            mp = self.state.get("mix_progress")
            frac = (mp["current"] / mp["total"]) if mp and mp["total"] else 0.0
            pct = 42 + 50 * frac
        elif status == "exporting":
            pct = 95
        elif status == "done":
            pct = 100
        elif status == "error":
            pct = self.state.get("percent", 0)
        else:
            pct = self.state.get("percent", 0)
        self.state["percent"] = round(min(pct, 100), 1)

        if status in ("done", "error"):
            self.state["eta_seconds"] = None
            return
        elapsed = time.time() - self.state["started_at"]
        if self.state["percent"] >= 4 and elapsed > 2:
            raw_eta = elapsed * (100 - self.state["percent"]) / self.state["percent"]
            self._eta_smoothed = raw_eta if self._eta_smoothed is None else (
                0.3 * raw_eta + 0.7 * self._eta_smoothed
            )
            self.state["eta_seconds"] = round(self._eta_smoothed)
        else:
            self.state["eta_seconds"] = None


def _kill_process_tree(proc: subprocess.Popen):
    """proc.kill() only signals the direct child — yt-dlp forks its own
    children (ffmpeg for audio conversion) that would otherwise be silently
    orphaned and keep running after we think we've killed a stalled/hung
    download. Confirmed live: a simulated hang left the forked child process
    still running after proc.kill() alone. Requires the process to have been
    started with start_new_session=True so the whole tree shares one process
    group and a single signal reaches all of it. POSIX only — same fallback
    convention already used by server.py's _shutdown_everything() for the
    same underlying reason (no os.killpg on Windows)."""
    if hasattr(os, "killpg"):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except ProcessLookupError:
            return  # already exited
    proc.kill()


def _download_with_progress(video_id: str, dest: Path, track: dict, ctx: JobContext):
    if dest.exists():
        track["download_status"] = "done"
        track["download_pct"] = 100
        ctx.publish(force=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--no-playlist", "--newline", "--remote-components", "ejs:github",
        "-o", str(dest.with_suffix("")) + ".%(ext)s",
    ]
    url = f"https://www.youtube.com/watch?v={video_id}"

    def _run(extra_args, label):
        track["download_status"] = "downloading"
        ctx.log_line(f"  {track['label']}: {label}")
        proc = subprocess.Popen(
            base_cmd + extra_args + [url],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            start_new_session=True,  # own process group — see _kill_process_tree
        )
        # Read stdout on a background thread into a queue instead of
        # iterating `proc.stdout` directly on this thread — a plain `for
        # line in proc.stdout` blocks with no timeout of its own, so a
        # yt-dlp process that goes quiet (stuck network read, no error ever
        # printed) would hang this whole job forever; the only other timeout
        # (proc.wait) is never even reached until stdout closes. Reading via
        # a queue lets us bound how long we wait for the NEXT line, not just
        # the process's total runtime.
        lines: queue.Queue = queue.Queue()

        def _reader():
            try:
                for raw_line in proc.stdout:
                    lines.put(raw_line)
            finally:
                lines.put(None)  # sentinel: stdout closed (process finishing)

        threading.Thread(target=_reader, daemon=True).start()

        last_err_lines = []
        deadline = time.monotonic() + DOWNLOAD_HARD_TIMEOUT_SEC
        while True:
            try:
                raw_line = lines.get(timeout=DOWNLOAD_IDLE_TIMEOUT_SEC)
            except queue.Empty:
                ctx.log_line(
                    f"  {track['label']}: no progress for {DOWNLOAD_IDLE_TIMEOUT_SEC}s — "
                    f"treating as stalled and killing it"
                )
                _kill_process_tree(proc)
                proc.wait(timeout=10)
                return 1, f"download stalled — no output for {DOWNLOAD_IDLE_TIMEOUT_SEC}s"
            if raw_line is None:
                break
            if time.monotonic() > deadline:
                ctx.log_line(
                    f"  {track['label']}: exceeded {DOWNLOAD_HARD_TIMEOUT_SEC}s hard cap — killing it"
                )
                _kill_process_tree(proc)
                proc.wait(timeout=10)
                return 1, f"download exceeded the {DOWNLOAD_HARD_TIMEOUT_SEC}s hard cap"
            line = raw_line.rstrip("\n")
            m = DOWNLOAD_PCT_RE.search(line)
            if m:
                track["download_pct"] = float(m.group(1))
                ctx.publish()
            elif "ERROR" in line or "error" in line.lower():
                last_err_lines.append(line)
        proc.wait(timeout=30)
        return proc.returncode, "\n".join(last_err_lines[-5:])

    rc, err = _run(["--cookies-from-browser", "chrome"], "downloading (using Chrome session)...")
    if not dest.exists():
        rc, err2 = _run([], "retrying without browser cookies...")
        err = err2 or err
    if not dest.exists():
        # A 403 here is often transient — YouTube rate-limiting, or (under
        # concurrent builds) contention reading Chrome's cookie DB from
        # multiple processes at once. One retry after a short, jittered
        # delay resolves it more often than not; not worth more than one.
        time.sleep(2 + random.random() * 3)
        rc, err3 = _run(["--cookies-from-browser", "chrome"], "retrying after a moment...")
        err = err3 or err

    if dest.exists():
        track["download_status"] = "done"
        track["download_pct"] = 100
    else:
        track["download_status"] = "error"
        track["download_error"] = err or "yt-dlp failed (see log)"
        ctx.log_line(f"  ✗ {track['label']}: download failed — {err[:200]}")
    ctx.publish(force=True)


def _normalize_loudness(path: Path):
    """Single-pass EBU R128 loudness normalization via ffmpeg, targeting a
    typical streaming-platform level (-14 LUFS). Best-effort: if it fails
    for any reason, the un-normalized file is left in place rather than
    losing the mix over a cosmetic step."""
    tmp = path.with_suffix(".normalized.mp3")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
             "-ar", "44100", "-b:a", "256k", str(tmp)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(path)
            print("  Loudness normalized to -14 LUFS.")
        else:
            print(f"  Loudness normalization skipped (ffmpeg exit {result.returncode}).")
            tmp.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001 — never lose the mix over this
        print(f"  Loudness normalization skipped: {type(e).__name__}: {e}")
        tmp.unlink(missing_ok=True)


def _tag_audio(path: Path, title: str, cover_image_path: Path | None):
    """Best-effort ID3 tags + embedded cover art (the AI story image, if
    one was generated). Never raises — tagging failure shouldn't lose the
    mix any more than normalization failure should."""
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, APIC

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        tags["TIT2"] = TIT2(encoding=3, text=title)
        tags["TPE1"] = TPE1(encoding=3, text="DJ Kyoko")
        tags["TALB"] = TALB(encoding=3, text=f"DJ Kyoko Mix — {time.strftime('%Y-%m-%d')}")

        has_cover = cover_image_path and cover_image_path.exists()
        if has_cover:
            tags["APIC"] = APIC(
                encoding=3, mime="image/jpeg", type=3, desc="Cover",
                data=cover_image_path.read_bytes(),
            )
        tags.save(str(path))
        print("  Tagged: title/artist/album" + (" + cover art" if has_cover else ""))
    except Exception as e:  # noqa: BLE001 — decorative, never fail the job over it
        print(f"  ID3 tagging skipped: {type(e).__name__}: {e}")


def _publish_to_gallery(ctx, out_path: Path, request_text: str):
    """Every finished mix ships to the shared Community gallery automatically
    — no manual Publish button. Best-effort: the audio file is already safe
    on disk, so a gallery failure here (offline, gallery down, etc.) is
    logged and never fails the job."""
    username = (USERNAME_FILE.read_text().strip() if USERNAME_FILE.exists() else "") or "Anonymous"

    duration_sec = 0.0
    try:
        from mutagen.mp3 import MP3
        duration_sec = MP3(str(out_path)).info.length
    except Exception:
        pass

    tracklist = [
        {"name": t.get("name"), "label": t.get("label"), "bpm": t.get("bpm")}
        for t in ctx.state.get("tracks", [])
    ]

    def _local_image(path: Path):
        try:
            return ("image.jpg", path.read_bytes(), "image/jpeg")
        except Exception:
            return None

    # story_image_url is now a local-server API path (see _save_story_image),
    # not a fetchable URL — read the same file straight off disk instead.
    story_image = _local_image(out_path.parent / "story_image.jpg")
    dj_image = None  # dj portrait generation is unused (see _generate_story_assets)

    try:
        with open(out_path, "rb") as f:
            files = {"audio": (out_path.name, f, "audio/mpeg")}
            if story_image:
                files["story_image"] = story_image
            if dj_image:
                files["dj_image"] = dj_image
            resp = requests.post(
                f"{GALLERY_URL}/api/publish",
                data={
                    "title": ctx.state.get("mix_name") or request_text,
                    "creator": username,
                    "request": request_text,
                    "narrative": ctx.state.get("narrative") or "",
                    "tracklist": json.dumps(tracklist),
                    "duration_sec": duration_sec,
                    "transition_markers_sec": json.dumps(ctx.state.get("transition_markers_sec") or []),
                },
                files=files,
                timeout=60,
            )
        resp.raise_for_status()
        print("  Published to the Community gallery.")
        ctx.set(published=True)
    except Exception as e:  # noqa: BLE001 — best-effort, never fail the job over it
        print(f"  (auto-publish to gallery failed: {type(e).__name__}: {e})")
        ctx.set(published=False)


def _save_story_image(root: Path, slug: str, url: str) -> bool:
    """Downloads the image bytes immediately and stores them permanently on
    our own disk. The URL Replicate/the AI gateway hands back is a temporary
    delivery link (confirmed: both plain replicate.delivery URLs and, more
    recently, presigned ai-gateway/Cloudflare R2 URLs with a 24h
    X-Amz-Expires) — persisting that URL string itself (as this used to do)
    means the image silently 404s for anyone who opens the mix again after
    it expires. Downloading now, while the link is fresh, is the only fix."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        dest = root / "output" / slug / "story_image.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except Exception:
        return False


def _generate_story_assets(ctx, request_text, tracks_state, api_key, base_url, model,
                            replicate_key, root, slug):
    """Best-effort creative flourishes — a mix name + narrative + two AI
    images. Runs in a background thread; never raises, never fails the mix.
    Each step is wrapped individually so one failure (e.g. Replicate being
    down) doesn't also take out the others."""
    try:
        story = generate_mix_story(request_text, tracks_state, api_key, model, base_url)
    except Exception as e:  # noqa: BLE001 — decorative feature, never fail the job over it
        ctx.log_line(f"  (mix name/story generation failed: {type(e).__name__}: {e})")
        story = None
    if story:
        ctx.set(mix_name=story["name"], narrative=story["narrative"])
        ctx.log_line(f'  Named it: "{story["name"]}"')

    if not replicate_key:
        ctx.log_line("  (no Replicate key configured — skipping AI image)")
        return
    if not story:
        return

    # Just one image — matching the mix's own narrative/description — not a
    # separate DJ portrait too. Simpler, cheaper, and halves the exposure to
    # the "background thread killed mid-flight if the job wraps up first"
    # failure mode (see _flux_image's own polling fix for why a call could
    # silently return nothing at all before that was fixed).
    try:
        image = generate_story_image(story["narrative"], replicate_key)
        if image and _save_story_image(root, slug, image):
            ctx.set(story_image_url=f"/api/jobs/{ctx.job_id}/image/story")
        elif image:
            ctx.log_line("  (story image generated but failed to save locally)")
        else:
            ctx.log_line("  (story image generation returned nothing usable)")
    except Exception as e:  # noqa: BLE001
        ctx.log_line(f"  (story image failed: {type(e).__name__}: {e})")


def _generate_voice_intros(ctx, request_text, build_tracks, api_key, base_url, model, elevenlabs_key, root, slug):
    """Best-effort: give every track its own short spoken DJ intro (Louis's
    cloned voice via ElevenLabs), referencing that track's title/artist and
    the mix's overall narrative — mixer/set_builder.py then ducks+overlays
    each one under that track's own quiet musical intro during assembly.

    One Claude call generates all the intro TEXTS together (cheaper, and
    keeps them coherent as one set — see mix_name/narrative reused as
    context). The TTS audio calls (one per track) are then parallelized via
    ThreadPoolExecutor per the workspace's HARD RULE on API-call loops.

    Every failure mode here (no key configured, the Claude call failing, any
    single TTS call failing) is caught and simply means fewer — or zero —
    tracks get a voice intro. This must never fail the mix build itself,
    same philosophy as _generate_story_assets above."""
    if not elevenlabs_key:
        print("  (no ElevenLabs key configured — skipping DJ voice intros)")
        return
    if not build_tracks:
        return

    # generate_mix_story (in _generate_story_assets, running concurrently
    # since story_thread.start() above) is one fast Claude call and usually
    # finishes long before track downloads do — wait a bounded amount for it
    # rather than either blocking forever or skipping outright if it's just
    # a little slow.
    for _ in range(40):  # up to 20s
        if ctx.state.get("narrative") or ctx.state.get("mix_name"):
            break
        time.sleep(0.5)
    mix_name = ctx.state.get("mix_name") or ""
    narrative = ctx.state.get("narrative") or ""

    try:
        intros = generate_track_intros(
            request_text, mix_name, narrative,
            [{"label": t["label"]} for t in build_tracks],
            api_key, model, base_url,
        )
    except Exception as e:  # noqa: BLE001 — decorative feature, never fail the job over it
        print(f"  (voice intro text generation failed: {type(e).__name__}: {e})")
        intros = None
    if not intros:
        print("  (voice intro text generation returned nothing usable — skipping voice intros)")
        return

    voice_dir = root / "downloads" / slug
    voice_dir.mkdir(parents=True, exist_ok=True)

    # Each worker only ever writes build_tracks[i] for its own i — disjoint
    # indices, no shared-state race, so no lock is needed here (unlike the
    # usual ThreadPoolExecutor pattern that writes into one shared dict/list).
    def _synth_one(i):
        try:
            audio_bytes = generate_track_intro_audio(intros[i], elevenlabs_key)
        except Exception as e:  # noqa: BLE001
            print(f"    (voice intro TTS failed for {build_tracks[i]['label']}: {type(e).__name__}: {e})")
            return
        if not audio_bytes:
            return
        path = voice_dir / f"voice_{build_tracks[i]['name']}.mp3"
        path.write_bytes(audio_bytes)
        build_tracks[i]["voice_path"] = str(path)

    with ThreadPoolExecutor(max_workers=min(8, len(build_tracks))) as ex:
        list(ex.map(_synth_one, range(len(build_tracks))))

    n_ok = sum(1 for t in build_tracks if t.get("voice_path"))
    print(f"  DJ voice intros: {n_ok}/{len(build_tracks)} generated")


def run_job(job_id, request_text, minutes, api_key, base_url, model, jobs_dict, root_dir,
            replicate_key=None, elevenlabs_key=None):
    ctx = JobContext(job_id, request_text, minutes, jobs_dict)
    os.chdir(root_dir)
    sys.stdout = _LiveLogWriter(ctx.log_line)
    sys.stderr = sys.stdout
    try:
        _run_job_body(ctx, request_text, minutes, api_key, base_url, model, root_dir, replicate_key, elevenlabs_key)
    except BillingCapError:
        ctx.error(
            "The shared API key hit its monthly budget cap. Enter your own free "
            "Anthropic API key in Settings to keep going.",
            error_type="billing_cap",
        )
    except Exception as e:  # noqa: BLE001 — surfacing to the UI is the point
        ctx.error(str(e))
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


MAX_CURATION_ATTEMPTS = 3  # 1 initial + 2 auto-retries on a BPM-gate failure


def _run_job_body(ctx, request_text, minutes, api_key, base_url, model, root_dir,
                   replicate_key=None, elevenlabs_key=None):
    slug = _slugify(request_text)
    # 2.3 min/track (was 3.2, briefly 2.6) with a floor of 4 (was 3) — the /2.6
    # pass still left short requests (~9min) landing on the bare minimum of 3
    # tracks, since round(9/2.6)==3 too. Confirmed live 2026-08-18: a 9-minute
    # "deep house sunset" request curated only 3 tracks even after that change.
    n_tracks = max(4, round(minutes / 2.3))
    root = Path(root_dir)

    for attempt in range(1, MAX_CURATION_ATTEMPTS + 1):
        retry_note = f" (auto-retry {attempt}/{MAX_CURATION_ATTEMPTS})" if attempt > 1 else ""
        ctx.set(status="curating", stage_label=f"Curating ~{n_tracks} tracks...{retry_note}")
        print(f"Curating ~{n_tracks} tracks for: {request_text!r}{retry_note}")
        validated = curate_and_validate(request_text, n_tracks, api_key, model, base_url)
        if len(validated) < 2:
            ctx.error(f"Only found {len(validated)} usable track(s) on YouTube — need at least 2. Try a different request.")
            return
        ok = _attempt_build(ctx, request_text, slug, validated, root, api_key, base_url, model,
                             replicate_key, elevenlabs_key, attempt)
        if ok is not False:
            return
        # ok is False only for a BPM-gate failure with attempts remaining — loop
        # around and re-curate a fresh set. Any other failure path already called
        # ctx.error()/returned inside _attempt_build.
    return


def _attempt_build(ctx, request_text, slug, validated, root, api_key, base_url, model,
                    replicate_key, elevenlabs_key, attempt):
    """One curate-download-build attempt. Returns True on success (job marked
    done/error terminally inside), False if this was a BPM-gate failure and the
    caller should re-curate and retry, or None (treated as True) if this attempt
    hit any other terminal outcome (already called ctx.error() and returned)."""
    tracks_state = [
        {
            "name": f"T{i+1:02d}",
            "label": f"{t['artist']} - {t['title']}",
            "bpm": t.get("approx_bpm"),
            "video_id": t["video_id"],
            "download_status": "pending",
            "download_pct": 0,
        }
        for i, t in enumerate(validated)
    ]
    ctx.set(tracks=tracks_state, status="downloading", stage_label="Downloading tracks...")
    print(f"{len(validated)} tracks confirmed on YouTube — downloading now.")

    # Narrative + AI images run in the background — decorative, shouldn't
    # slow down the actual download/mix critical path. Joined with a bounded
    # timeout near the end so they usually land before the job reports done.
    story_thread = threading.Thread(
        target=_generate_story_assets,
        args=(ctx, request_text, tracks_state, api_key, base_url, model, replicate_key, root, slug),
        daemon=True,
    )
    story_thread.start()

    build_tracks = []
    for i, (t, ts) in enumerate(zip(validated, tracks_state)):
        dest = root / "downloads" / slug / f"{t['video_id']}.mp3"
        _download_with_progress(t["video_id"], dest, ts, ctx)
        if ts["download_status"] != "done":
            # One bad/blocked track shouldn't kill a whole mix — skip it and
            # keep going. We only give up if too few tracks survive overall.
            print(f"  Skipping '{ts['label']}' — {ts.get('download_error', 'unknown error')}")
            continue
        build_tracks.append({
            "name": ts["name"], "label": ts["label"], "path": str(dest), "hint": t.get("approx_bpm"),
        })

    if len(build_tracks) < 2:
        failed = [t["label"] for t in tracks_state if t["download_status"] != "done"]
        ctx.error(
            f"Only {len(build_tracks)} track(s) downloaded successfully — need at least 2. "
            f"Failed: {', '.join(failed)}"
        )
        return
    if len(build_tracks) < len(tracks_state):
        print(f"  Continuing with {len(build_tracks)}/{len(tracks_state)} tracks (some were skipped).")

    _generate_voice_intros(ctx, request_text, build_tracks, api_key, base_url, model,
                            elevenlabs_key, root, slug)

    brain = _Brain(
        style_name=slug, set_name=slug,
        notes=f'A mix built from the request: "{request_text}"', tracks=build_tracks,
    )
    ctx.set(status="mixing", stage_label="Beat-matching tracks...",
            mix_progress={"current": 0, "total": max(1, len(build_tracks) - 1), "label": ""})
    print(f"Building mix ({len(build_tracks)} tracks)...")
    try:
        build_full_set(brain)
    except ValueError as e:
        if not str(e).startswith("BPM too far"):
            raise
        print(f"  {e}")
        if attempt < MAX_CURATION_ATTEMPTS:
            print(f"  Even the widened tempo-bridge couldn't cover this gap — "
                  f"auto-retrying with a fresh set ({attempt}/{MAX_CURATION_ATTEMPTS})...")
            return False
        skipped_note = ""
        if len(build_tracks) < len(tracks_state):
            failed = [t["label"] for t in tracks_state if t["download_status"] != "done"]
            skipped_note = (
                f" ({', '.join(failed)} couldn't be downloaded, which broke the tempo "
                f"bridge between the tracks that were left.)"
            )
        ctx.error(
            f"Tried {MAX_CURATION_ATTEMPTS} different track sets and two tracks were still "
            f"too far apart in tempo to blend cleanly, even with a tempo bridge."
            f"{skipped_note} Hit Retry — it'll try fresh sets again."
        )
        return

    out_path = root / "output" / slug / "FULL_SET.mp3"
    ctx.set(status="exporting", stage_label="Finalizing...")
    if not out_path.exists():
        ctx.error("Mix finished but the output file is missing — check the log.")
        return

    _normalize_loudness(out_path)

    # Give the narrative/images a bounded window to land before reporting
    # done — mixing usually takes longer than this anyway, so in practice
    # they're already finished; this just guards against the rare case
    # where they're still running when the audio work wraps up early.
    # 100s: the two Replicate image calls now run in parallel (each capped at
    # 90s) instead of sequentially, so this only needs to cover one call's
    # worst case, not two stacked — but must still exceed it, or a fast mix
    # can finalize (and the OS process exit) while the thread is still
    # mid-flight, silently killing it with no error logged (confirmed live).
    story_thread.join(timeout=100)

    title = ctx.state.get("mix_name") or request_text
    _tag_audio(out_path, title, out_path.parent / "story_image.jpg")

    display_name = re.sub(r'[^\w\s-]', '', title).strip()
    display_name = re.sub(r'[-\s]+', ' ', display_name)[:80] or "DJ Kyoko Mix"
    named_path = out_path.with_name(f"{display_name}.mp3")
    if named_path != out_path:
        out_path.rename(named_path)
        out_path = named_path

    rel = str(out_path.relative_to(root))

    transition_markers_sec = []
    cue_points_path = out_path.parent / "cue_points.json"
    if cue_points_path.exists():
        try:
            transition_markers_sec = json.loads(cue_points_path.read_text()).get("transition_markers_sec", [])
        except Exception as e:  # noqa: BLE001 — decorative UI data, never fail the job over it
            print(f"  (cue points failed to load: {type(e).__name__}: {e})")

    ctx.set(
        status="done", stage_label="Done!", percent=100, eta_seconds=None,
        output_rel_path=rel, transition_markers_sec=transition_markers_sec,
    )
    print(f"Done: {rel}")

    _publish_to_gallery(ctx, out_path, request_text)
