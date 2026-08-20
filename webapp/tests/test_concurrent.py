"""
Real end-to-end tests for the DJ Kyoko web UI's concurrency and curation
behavior — no mocking. Starts a real server (on a separate port from any
live user session), submits real jobs, does real curation API calls, real
YouTube downloads, and real audio mixing, then checks real output files.

This is deliberately expensive (network calls, downloads, CPU-bound audio
work) — that's the point: it's the only way to actually prove concurrency
and the curation rules work, not just that the code parses.

Run (from the djbot repo root, with the project venv active):
    pytest webapp/tests/test_concurrent.py -v -s -m slow

Or standalone:
    python webapp/tests/test_concurrent.py
"""
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent.parent  # djbot/
WEBAPP_DIR = ROOT / "webapp"
sys.path.insert(0, str(ROOT))

PORT = 8935  # deliberately different from the live app's 8934
BASE = f"http://127.0.0.1:{PORT}"
SHARED_KEY_FILE = WEBAPP_DIR / ".shared_key"
PROXY_URL = "https://spend-proxy-production.up.railway.app/v1/messages"


@pytest.fixture(scope="module")
def server():
    env = {**os.environ, "DJBOT_APP_SUPPORT": str(Path.home() / "Library" / "Application Support" / "DJ Kyoko")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(WEBAPP_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    up = False
    for _ in range(60):
        try:
            if requests.get(f"{BASE}/health", timeout=1).status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    if not up:
        proc.kill()
        out = proc.stdout.read() if proc.stdout else ""
        raise RuntimeError(f"test server on port {PORT} never came up:\n{out}")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def _submit(request_text, minutes=8):
    r = requests.post(f"{BASE}/api/jobs", json={"request": request_text, "minutes": minutes}, timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _get(job_id):
    r = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def _poll_until_all_terminal(job_ids, timeout=1800):
    # Multiple live-diagnosed runs on this 10-core machine showed real,
    # highly variable completion times under two genuinely concurrent
    # CPU/disk/network-bound mixes (torch beat detection, rubberband
    # time-stretch, yt-dlp downloads + Chrome cookie access) — anywhere
    # from ~4 min to 20+ min for the slower of the two, vs ~3-4 min solo.
    # That's real resource contention on a personal laptop, not a hang:
    # every run either completed with a valid output file or failed with a
    # legitimate quality-gate rejection — never silently stuck. Given that,
    # this timeout exists only as a final backstop against an actual
    # hang/deadlock, not as a performance gate — don't tighten it chasing
    # a "fast" number; speed here is inherently environment-dependent.
    deadline = time.time() + timeout
    saw_two_active_at_once = False
    last_states = {}
    while time.time() < deadline:
        last_states = {jid: _get(jid) for jid in job_ids}
        actively_running = [s for s in last_states.values() if s["status"] not in ("queued", "done", "error")]
        if len(actively_running) >= 2:
            saw_two_active_at_once = True
        if all(s["status"] in ("done", "error") for s in last_states.values()):
            return last_states, saw_two_active_at_once
        time.sleep(3)
    statuses = {jid: s["status"] for jid, s in last_states.items()}
    raise TimeoutError(f"jobs didn't finish within {timeout}s: {statuses}")


_LEGITIMATE_ERROR_SUBSTRINGS = (
    "BPM too far", "need at least 2", "Only found",
)


@pytest.mark.slow
def test_two_concurrent_mixes_run_in_parallel_and_produce_real_output(server):
    id_a = _submit("test-concurrency lofi hip hop A", minutes=8)
    id_b = _submit("test-concurrency 80s synthwave B", minutes=8)

    states, saw_concurrent = _poll_until_all_terminal([id_a, id_b])

    assert saw_concurrent, (
        "never observed both jobs in an active (non-queued) state at the same "
        "time — concurrency is broken, not just slow"
    )

    for jid, s in states.items():
        assert s["status"] in ("done", "error"), f"{jid} ended in unexpected status: {s['status']}"
        if s["status"] == "error":
            err = s["error"] or ""
            assert any(sub in err for sub in _LEGITIMATE_ERROR_SUBSTRINGS), (
                f"{jid} failed with an error that isn't one of the known-legitimate "
                f"rejections (quality gate / too few tracks) — likely a real bug: {err}"
            )
        else:
            out = ROOT / s["output_rel_path"]
            assert out.exists(), f"{jid} reported done but its output file is missing: {out}"
            assert out.stat().st_size > 200_000, (
                f"{jid} output file suspiciously small ({out.stat().st_size} bytes) — likely corrupt"
            )


@pytest.mark.slow
def test_delete_removes_a_job():
    jid = _submit("test-concurrency delete-me", minutes=6)
    assert requests.get(f"{BASE}/api/jobs/{jid}", timeout=10).status_code == 200
    r = requests.delete(f"{BASE}/api/jobs/{jid}", timeout=10)
    assert r.status_code == 200
    assert requests.get(f"{BASE}/api/jobs/{jid}", timeout=10).status_code == 404


@pytest.mark.slow
def test_curation_spreads_artists_and_blends_beyond_the_two_named():
    """Cheaper than a full mix test — exercises only curation, not
    download/mixing, since that's what the artist-blending rules affect."""
    from mixer.curate import curate_and_validate

    api_key = base64.b64decode(SHARED_KEY_FILE.read_bytes()).decode()
    tracks = curate_and_validate("billie eilish meets the weeknd", 6, api_key, "claude-sonnet-5", PROXY_URL)
    assert len(tracks) >= 4, f"too few tracks came back validated: {len(tracks)}"

    for i in range(1, len(tracks)):
        prev_artist = tracks[i - 1]["artist"].strip().lower()
        cur_artist = tracks[i]["artist"].strip().lower()
        assert prev_artist != cur_artist, (
            f"adjacent same-artist tracks at position {i}: "
            f"{tracks[i-1]['artist']} - {tracks[i-1]['title']} / {tracks[i]['artist']} - {tracks[i]['title']}"
        )

    artists = {t["artist"].strip().lower() for t in tracks}
    named = {"billie eilish", "the weeknd"}
    assert artists - named, (
        f"curator only used the two named artists — no blend with other artists: {artists}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s", "-m", "slow"]))
