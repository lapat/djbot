"""
DJ Kyoko web UI — local FastAPI server.

Runs each mix build in its own OS process (true multiprocessing, not
threads) so multiple mixes genuinely progress in parallel and CPU-heavy
audio work (beat detection, time-stretching) on one job never blocks
another. A bounded number run concurrently (MAX_CONCURRENT); the rest wait
as "queued" and start automatically as slots free up.
"""
import base64
import io
import json
import multiprocessing as mp
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from job_runner import run_job, _slugify

BUILD_TAG = "2026-08-22-robustness-pass-v1"

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
APP_SUPPORT = Path(os.environ.get(
    "DJBOT_APP_SUPPORT",
    str(Path.home() / "Library" / "Application Support" / "DJ Kyoko"),
))
APP_SUPPORT.mkdir(parents=True, exist_ok=True)

# Where job data (downloads/, output/, beatgrid/tag caches) actually gets
# written. Deliberately NOT the same as ROOT_DIR when running as the signed
# Mac .app: macOS App Translocation runs a downloaded/quarantined .app from a
# randomized, READ-ONLY copy of its own bundle path — any write under
# ROOT_DIR (which lives inside Contents/Resources) fails with
# "[Errno 30] Read-only file system" the moment a real job tries to download
# a track. mac_app/DJ Kyoko.command sets DJBOT_DATA_DIR to a path under
# APP_SUPPORT (always writable, outside the bundle) to avoid this. Defaults
# to ROOT_DIR for local dev and the Windows build, neither of which has this
# translocation problem.
DATA_DIR = Path(os.environ.get("DJBOT_DATA_DIR", str(ROOT_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_SUPPORT / "web_config.json"
HISTORY_FILE = APP_SUPPORT / "history.json"

PROXY_URL = "https://spend-proxy-production.up.railway.app/v1/messages"
SHARED_KEY_FILE = ROOT_DIR / "webapp" / ".shared_key"
REAL_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MAX_CONCURRENT = int(os.environ.get("DJBOT_MAX_CONCURRENT", "2"))

app = FastAPI()

_manager = mp.Manager()
jobs = _manager.dict()          # job_id -> state dict (published by job_runner)
_processes: dict[str, mp.Process] = {}
_queue_order: list[str] = []    # job_ids waiting for a free slot, in submit order
_history_lock = threading.Lock()

# ── shut down when the app window closes ────────────────────────────────
# The web UI's job cards no longer leave a truly "closed" window running
# invisibly in the background — see /api/shutdown and /api/heartbeat below.
_last_seen = time.time()
IDLE_SHUTDOWN_SEC = 30  # frontend heartbeats every 5s — generous margin for a slow tick


def _any_job_active() -> bool:
    # A job counts as "active" until its gallery publish has actually
    # resolved (published is None while _publish_to_gallery() is still
    # running in the job's own process — see job_runner.py), not just until
    # status flips to "done". Confirmed live 2026-08-19: without this, the
    # idle-shutdown watcher killed the whole process group (including the
    # still-uploading publish call) in the few seconds between a job
    # finishing and its publish completing — the finished mix was correct
    # on disk but never made it to the gallery. Only guards the IDLE-timeout
    # path; the explicit close-triggered shutdown (see /api/shutdown) stays
    # immediate and unconditional, per intent — a user closing the window
    # mid-build/mid-publish is a real "stop everything" signal, not idle
    # neglect.
    return any(
        s.get("status") not in ("done", "error") or s.get("published") is None
        for s in jobs.values()
    )


def _shutdown_everything():
    # A plain os._exit(0) here would only kill THIS process — daemon=True
    # only makes multiprocessing clean up child job processes on a NORMAL
    # interpreter exit (via its atexit hook), which os._exit() deliberately
    # skips. An in-progress build's job process (and the yt-dlp/ffmpeg/
    # rubberband subprocesses it shells out to) would be silently orphaned
    # and keep running invisibly — exactly the bug this whole feature exists
    # to fix. Killing the whole POSIX process group instead reuses the same
    # mechanism Terminal already uses when its window closes (it sends
    # SIGHUP to the foreground process group) — every child here inherits
    # that same group by default, so one signal reaches all of them.
    if hasattr(os, "killpg"):  # POSIX only — Windows has no process-group signaling
        try:
            os.killpg(os.getpgid(0), signal.SIGTERM)
            return
        except Exception:  # noqa: BLE001 — fall through to the blunter fallback below
            pass
    for p in _processes.values():
        if p.is_alive():
            p.terminate()
    os._exit(0)


def _idle_watcher():
    while True:
        time.sleep(5)
        if time.time() - _last_seen > IDLE_SHUTDOWN_SEC and not _any_job_active():
            _shutdown_everything()


threading.Thread(target=_idle_watcher, daemon=True).start()


def _load_history_into_jobs():
    """On startup, restore completed mixes from disk so they're browsable
    as a library across restarts. Anything that was still queued/running
    when the server last stopped is dropped — its process no longer exists,
    so there's nothing to resume."""
    if not HISTORY_FILE.exists():
        return
    try:
        saved = json.loads(HISTORY_FILE.read_text())
    except Exception:
        return
    for job_id, state in saved.items():
        if state.get("status") in ("done", "error"):
            state["restored_from_history"] = True
            jobs[job_id] = state


def _save_history():
    with _history_lock:
        try:
            HISTORY_FILE.write_text(json.dumps(dict(jobs)))
        except Exception:
            pass  # history is a convenience, never worth failing a request over


def _history_saver_loop():
    while True:
        time.sleep(5)
        if any(s.get("status") in ("done", "error") for s in jobs.values()):
            _save_history()


_load_history_into_jobs()
threading.Thread(target=_history_saver_loop, daemon=True).start()


# ── config (API key source) ─────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {"key_source": None, "own_key": None}


def _save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg))


def _resolve_key():
    cfg = _load_config()
    if cfg.get("key_source") == "own" and cfg.get("own_key"):
        return cfg["own_key"], REAL_ANTHROPIC_URL
    if SHARED_KEY_FILE.exists():
        token = base64.b64decode(SHARED_KEY_FILE.read_bytes()).decode()
        return token, PROXY_URL
    return None, REAL_ANTHROPIC_URL


# Deliberately NOT under webapp/ — this file never ships in the friend zip.
# A raw personal Replicate token baked into a distributable app would let
# anyone who has it spend Louis's Replicate credits with no cap at all.
REPLICATE_KEY_FILE = APP_SUPPORT / "replicate_key.txt"


def _resolve_replicate_key():
    if REPLICATE_KEY_FILE.exists():
        return REPLICATE_KEY_FILE.read_text().strip() or None
    return None


# Same reasoning as REPLICATE_KEY_FILE above — deliberately NOT under
# webapp/ so it never ships in the friend zip. Powers the optional DJ
# voice-intro feature (mixer/voice.py + set_builder.py's ducking).
ELEVENLABS_KEY_FILE = APP_SUPPORT / "elevenlabs_key.txt"


def _resolve_elevenlabs_key():
    if ELEVENLABS_KEY_FILE.exists():
        return ELEVENLABS_KEY_FILE.read_text().strip() or None
    return None


# ── gallery (shared mixes with friends) ─────────────────────────────────────
# Separate file from web_config.json (API key settings) deliberately — that
# file gets fully overwritten on every /api/config POST, so anything sharing
# it would risk being silently wiped by an unrelated settings change.
USERNAME_FILE = APP_SUPPORT / "username.txt"
GALLERY_URL = os.environ.get("DJBOT_GALLERY_URL", "https://djbot-gallery-production.up.railway.app")


def _get_username() -> str | None:
    if USERNAME_FILE.exists():
        return USERNAME_FILE.read_text().strip() or None
    return None


_recent_surprises: list[str] = []  # avoid repeating the last few AI-generated picks

SURPRISE_SYSTEM_PROMPT = """You are a music curator with wildly eclectic, encyclopedic \
taste across every genre and era. Generate ONE short, surprising DJ mix request — \
the kind of prompt someone would type into an AI DJ app to build a beat-matched mix. \
3 to 9 words. Can name real artists/genres/eras in an "X meets Y" style, or describe \
a vibe/scene/moment. Be genuinely varied and unexpected — avoid generic phrasing \
("chill vibes", "party mix") and avoid anything on the recently-used list below.

Return ONLY the prompt text itself — no quotes, no punctuation at the end, no \
explanation, nothing else."""


@app.get("/api/surprise")
def surprise_prompt():
    api_key, base_url = _resolve_key()
    if not api_key:
        raise HTTPException(400, "No API key configured yet — set one up in Settings first.")
    avoid = "\n".join(f"- {p}" for p in _recent_surprises[-15:]) or "(none yet)"
    try:
        resp = requests.post(
            base_url,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": "claude-sonnet-5", "max_tokens": 60,
                "thinking": {"type": "disabled"},
                "system": SURPRISE_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"Recently used, don't repeat:\n{avoid}"}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
        text = text.strip('"\'').strip()
    except Exception as e:  # noqa: BLE001 — surfacing to the UI is the point
        raise HTTPException(502, f"Couldn't generate a surprise: {type(e).__name__}") from e
    if not text:
        raise HTTPException(502, "Empty response — try again")
    _recent_surprises.append(text)
    del _recent_surprises[:-20]
    return {"prompt": text}


class ConfigIn(BaseModel):
    key_source: str  # "shared" | "own"
    own_key: str | None = None


class ShareIn(BaseModel):
    recipient: str


@app.get("/api/config")
def get_config():
    cfg = _load_config()
    return {"configured": cfg.get("key_source") is not None, "key_source": cfg.get("key_source")}


@app.post("/api/config")
def set_config(cfg: ConfigIn):
    if cfg.key_source not in ("shared", "own"):
        raise HTTPException(400, "key_source must be 'shared' or 'own'")
    if cfg.key_source == "own" and not (cfg.own_key or "").strip():
        raise HTTPException(400, "own_key required when key_source is 'own'")
    _save_config({"key_source": cfg.key_source, "own_key": (cfg.own_key or "").strip() or None})
    return {"ok": True}


class ElevenLabsKeyIn(BaseModel):
    api_key: str


@app.get("/api/config/elevenlabs")
def get_elevenlabs_config():
    return {"configured": _resolve_elevenlabs_key() is not None}


@app.post("/api/config/elevenlabs")
def set_elevenlabs_config(body: ElevenLabsKeyIn):
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "api_key required")
    ELEVENLABS_KEY_FILE.write_text(key)
    return {"ok": True}


@app.delete("/api/config/elevenlabs")
def clear_elevenlabs_config():
    ELEVENLABS_KEY_FILE.unlink(missing_ok=True)
    return {"ok": True}


# ── job orchestration ────────────────────────────────────────────────────────

class JobIn(BaseModel):
    request: str
    minutes: float = 30.0


_pump_lock = threading.Lock()


def _pump_queue():
    """Start queued jobs while there's a free concurrency slot.

    Called from multiple request threads (create_job, list_jobs, and every
    open SSE stream's poll loop) — starlette runs sync route handlers in a
    thread pool, so without a lock two threads could both observe a free
    slot and double-start a job. jobs/_processes/_queue_order are plain
    dict/list, not thread-safe on their own.
    """
    with _pump_lock:
        running = sum(1 for p in _processes.values() if p.is_alive())
        while _queue_order and running < MAX_CONCURRENT:
            job_id = _queue_order.pop(0)
            state = dict(jobs.get(job_id, {}))
            if not state:
                continue
            api_key, base_url = _resolve_key()
            replicate_key = _resolve_replicate_key()
            elevenlabs_key = _resolve_elevenlabs_key()
            p = mp.Process(
                target=run_job,
                args=(job_id, state["request"], state["minutes"], api_key, base_url, "claude-sonnet-5",
                      jobs, str(DATA_DIR), replicate_key, elevenlabs_key),
                daemon=True,
            )
            _processes[job_id] = p
            p.start()
            running += 1


@app.post("/api/jobs")
def create_job(body: JobIn):
    if not body.request.strip():
        raise HTTPException(400, "request text is required")
    api_key, _ = _resolve_key()
    if not api_key:
        raise HTTPException(400, "No API key configured yet — set one up in Settings first.")

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "id": job_id, "request": body.request.strip(), "minutes": body.minutes,
        "status": "queued", "stage_label": "Queued...", "created_at": time.time(),
        "started_at": time.time(), "tracks": [], "log": [], "percent": 0,
        "eta_seconds": None, "error": None, "error_type": None, "output_rel_path": None,
        "narrative": None, "mix_name": None, "story_image_url": None, "dj_image_url": None,
        "published": None,
    }
    _queue_order.append(job_id)
    _pump_queue()
    return {"id": job_id}


@app.get("/api/jobs")
def list_jobs():
    _pump_queue()
    return sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "unknown job")
    return jobs[job_id]


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "unknown job")
    if job_id in _queue_order:
        _queue_order.remove(job_id)
    p = _processes.pop(job_id, None)
    if p is not None and p.is_alive():
        p.terminate()
    del jobs[job_id]
    _save_history()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry-with-own-key")
def retry_with_own_key(job_id: str, cfg: ConfigIn):
    if job_id not in jobs:
        raise HTTPException(404, "unknown job")
    if cfg.key_source != "own" or not (cfg.own_key or "").strip():
        raise HTTPException(400, "own_key required")
    _save_config({"key_source": "own", "own_key": cfg.own_key.strip()})
    state = dict(jobs[job_id])
    new_id = uuid.uuid4().hex[:12]
    jobs[new_id] = {
        **state, "id": new_id, "status": "queued", "stage_label": "Queued...",
        "created_at": time.time(), "started_at": time.time(), "tracks": [], "log": [],
        "percent": 0, "eta_seconds": None, "error": None, "error_type": None,
        "output_rel_path": None, "narrative": None, "mix_name": None, "story_image_url": None, "dj_image_url": None,
        "published": None,
    }
    _queue_order.append(new_id)
    _pump_queue()
    return {"id": new_id}


@app.get("/api/jobs/{job_id}/stream")
def stream_job(job_id: str):
    def gen():
        last_payload = None
        idle = 0
        while True:
            _pump_queue()
            state = jobs.get(job_id)
            if state is None:
                yield "event: error\ndata: {}\n\n"
                return
            payload = json.dumps(state)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
                idle = 0
            else:
                idle += 1
            if state["status"] in ("done", "error"):
                return
            time.sleep(0.35)
            if idle > 0 and idle % 20 == 0:
                yield ": keep-alive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@app.get("/api/jobs/{job_id}/audio")
def get_audio(job_id: str):
    state = jobs.get(job_id)
    if not state or not state.get("output_rel_path"):
        raise HTTPException(404, "not ready")
    path = DATA_DIR / state["output_rel_path"]
    if not path.exists():
        raise HTTPException(404, "file missing")
    # inline (not attachment) — an attachment disposition breaks native <audio>
    # seek/scrub in some browsers even though the byte-range support is identical
    return FileResponse(
        path, media_type="audio/mpeg",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@app.get("/api/jobs/{job_id}/image/{kind}")
def get_job_image(job_id: str, kind: str):
    """Serves the AI-generated mix image from our own permanent local copy
    (see _save_story_image in job_runner.py) instead of the temporary
    Replicate/AI-gateway delivery URL, which expires within hours/a day and
    used to be stored (and shown) directly. Keyed off the request text's
    slug — same directory job_runner.py itself writes to — rather than
    output_rel_path, so the image is servable while a job is still running,
    not just once it's fully done."""
    if kind not in ("story", "dj"):
        raise HTTPException(404, "unknown image kind")
    state = jobs.get(job_id)
    if not state:
        raise HTTPException(404, "job not found")
    slug = _slugify(state.get("request") or "")
    path = DATA_DIR / "output" / slug / f"{kind}_image.jpg"
    if not path.exists():
        raise HTTPException(404, "image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/reveal")
def reveal_in_finder(job_id: str):
    state = jobs.get(job_id)
    if not state or not state.get("output_rel_path"):
        raise HTTPException(404, "not ready")
    path = DATA_DIR / state["output_rel_path"]
    if sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)])
    else:
        subprocess.run(["xdg-open", str(path.parent)])
    return {"ok": True}


@app.get("/api/jobs/{job_id}/tracks-zip")
def get_tracks_zip(job_id: str):
    """The individual source tracks + the cue sheet, for someone who wants
    the raw ingredients rather than just the finished blend."""
    state = jobs.get(job_id)
    if not state or not state.get("output_rel_path"):
        raise HTTPException(404, "not ready")
    slug = Path(state["output_rel_path"]).parent.name
    downloads_dir = DATA_DIR / "downloads" / slug
    output_dir = DATA_DIR / "output" / slug
    notes_path = output_dir / "SET_NOTES.txt"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for t in state.get("tracks", []):
            src = downloads_dir / f"{t['video_id']}.mp3"
            if src.exists():
                safe_label = re.sub(r'[/\\:*?"<>|]', "-", t.get("label", t["name"]))
                zf.write(src, arcname=f"{t['name']} - {safe_label}.mp3")
        if notes_path.exists():
            zf.write(notes_path, arcname="SET_NOTES.txt")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}_tracks.zip"'},
    )


def _finished_audio_path(job_id: str) -> Path:
    state = jobs.get(job_id)
    if not state or not state.get("output_rel_path"):
        raise HTTPException(404, "not ready")
    path = DATA_DIR / state["output_rel_path"]
    if not path.exists():
        raise HTTPException(404, "file missing")
    return path


@app.get("/api/gallery-config")
def gallery_config():
    return {"gallery_url": GALLERY_URL, "username": _get_username()}


class UsernameIn(BaseModel):
    username: str


@app.post("/api/config/username")
def set_username(body: UsernameIn):
    name = body.username.strip()
    if not name:
        raise HTTPException(400, "username required")
    if len(name) > 40:
        raise HTTPException(400, "keep it under 40 characters")
    USERNAME_FILE.write_text(name)
    return {"ok": True, "username": name}


# Every finished mix is auto-published to the gallery from job_runner.py itself
# (right after status="done") — see `_publish_to_gallery` there. No manual
# endpoint needed here anymore.


@app.post("/api/jobs/{job_id}/share/imessage")
def share_imessage(job_id: str, body: ShareIn):
    path = _finished_audio_path(job_id)
    recipient = body.recipient.strip()
    if not recipient:
        raise HTTPException(400, "recipient required")
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{recipient}" of targetService
        send POSIX file "{path}" to targetBuddy
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise HTTPException(500, f"iMessage send failed: {result.stderr.strip()[:300]}")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/share/email")
def share_email(job_id: str, body: ShareIn):
    path = _finished_audio_path(job_id)
    recipient = body.recipient.strip()
    if not recipient:
        raise HTTPException(400, "recipient required")
    state = jobs.get(job_id) or {}
    subject = f"Mix: {state.get('mix_name') or state.get('request') or 'DJ Kyoko mix'}"
    # visible:true and no `send` call — opens a real compose window for the
    # user to review before sending, rather than firing an email blind.
    script = f'''
    tell application "Mail"
        set newMsg to make new outgoing message with properties {{subject:"{subject}", visible:true}}
        tell newMsg
            make new to recipient with properties {{address:"{recipient}"}}
            make new attachment with properties {{file name:POSIX file "{path}"}} at after the last paragraph
        end tell
        activate
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise HTTPException(500, f"Email compose failed: {result.stderr.strip()[:300]}")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text()


@app.get("/api/build")
def build_info():
    return {"build": BUILD_TAG}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/heartbeat")
def heartbeat():
    global _last_seen
    _last_seen = time.time()
    return {"ok": True}


@app.post("/api/shutdown")
def shutdown():
    # Fired by the page's own `pagehide` handler the instant the window
    # actually closes — an unambiguous "the user just closed this" signal,
    # unlike the heartbeat timeout, so this always shuts down immediately,
    # even mid-build. Reply first, then shut down on a short delay so the
    # sendBeacon request the browser is holding open doesn't get cut off.
    threading.Timer(0.3, _shutdown_everything).start()
    return {"ok": True}
