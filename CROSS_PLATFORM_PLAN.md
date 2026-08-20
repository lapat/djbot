# DJ Kyoko — Cross-Platform Plan (Windows + iPad/iPhone)

Researched 2026-08-18. This doc is honest about what's verified vs. assumed — I have
no Windows machine, so anything marked "UNVERIFIED" needs a real test on a real PC
before shipping to a friend.

## TL;DR

- **Windows: fully feasible, no core Python code changes needed.** The one real
  blocker (rubberband has no winget/choco package) has a clean fix: Rubber Band's
  own site ships a prebuilt Windows zip. Needs a new `.bat`/`.ps1` launcher
  (parallel to the existing `.command` file) and real testing on a Windows box —
  I cannot verify this myself.
- **iPad/iPhone as a native app: not feasible without a full rewrite.** App Store
  sandboxing blocks exactly what this app needs (spawning ffmpeg/rubberband/deno
  as subprocesses). Confirmed via Apple's own Guideline 2.5.2.
- **iPad/iPhone as a *client*: trivial, and mostly already works.** Keep the Mac
  running the existing server, bind it to `0.0.0.0` instead of `127.0.0.1`, and
  hit it from the phone/iPad browser over the Tailscale tailnet Louis already has
  set up. One required code change (the bind host), everything else checks out.

---

## Part 1 — Windows

### What already works, unmodified

Checked every subprocess call in the codebase (`mixer/download.py`,
`mixer/curate.py`, `webapp/job_runner.py`) — `yt-dlp`, `ffmpeg`, and `rubberband`
(via `pyrubberband`) are all invoked by bare command name resolved through `PATH`,
never a hardcoded Unix path like `/usr/local/bin/ffmpeg`. That means once the three
binaries are installed and on `PATH`, the Python side needs **zero changes** to run
on Windows. `librosa`, `numpy`, `soundfile`, `scipy`, `pydub`, `pyrubberband`,
`beat-this` (torch), `mutagen`, `fastapi`, `uvicorn` are all pure-Python/pip
packages with existing Windows wheels — not a concern.

### The dependency story, tool by tool

| Tool | Windows path | Verified? |
|---|---|---|
| **ffmpeg** | `winget install Gyan.FFmpeg` (well-known, widely-used winget package) | Package existence confirmed via search; install behavior UNVERIFIED (no Windows box to test) |
| **deno** | `winget install DenoLand.Deno`, or the official installer `irm https://deno.land/install.ps1 \| iex` | Both methods confirmed to exist in Deno's own docs |
| **rubberband** | **No winget/choco package exists** (confirmed — searched both). Fix: Rubber Band's own site ships a prebuilt zip: `https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip` — download + `Expand-Archive` it into the app's support folder, add that folder to `PATH` for the launcher's process (same pattern brew uses on Mac, just manual instead of a package manager) | Download URL confirmed live and described as "Windows executable for the Rubber Band utility program." Actual unzip/run behavior UNVERIFIED. |
| **python3** | `winget install Python.Python.3.11` if missing | UNVERIFIED |
| **Chrome cookies** (`yt-dlp --cookies-from-browser chrome`) | yt-dlp has native Windows DPAPI decryption for Chrome's encrypted cookie store — this is a real, maintained code path, not a gap. One known edge case: yt-dlp GitHub issue #7271 reports "Permission denied" when Chrome is open at the same time as the extraction attempt on Windows. Mitigation: tell the user to close Chrome before first launch, and keep the existing Mac fallback logic (retry without `--cookies-from-browser` if it fails) — already in `mixer/download.py`. | Confirmed via yt-dlp's issue tracker + docs. Not tested live. |

### The launcher — `.bat`/PowerShell equivalent of `DJ Kyoko.command`

Same shape as the Mac launcher: check for each dependency, install if missing, set
up a venv, pip install, launch uvicorn, open the browser. Draft (untested):

```bat
@echo off
setlocal
cd /d "%~dp0"
set APPDATA_DIR=%LOCALAPPDATA%\DJ Kyoko
set VENV=%APPDATA_DIR%\venv
set RB_DIR=%APPDATA_DIR%\rubberband
set PORT=8934

where ffmpeg >nul 2>nul || winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
where deno >nul 2>nul || winget install --id DenoLand.Deno -e --accept-source-agreements --accept-package-agreements

where rubberband >nul 2>nul
if errorlevel 1 (
  powershell -Command "Invoke-WebRequest -Uri https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip -OutFile '%TEMP%\rb.zip'; Expand-Archive -Path '%TEMP%\rb.zip' -DestinationPath '%RB_DIR%' -Force"
  set "PATH=%RB_DIR%;%PATH%"
)

where python >nul 2>nul || winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements

if not exist "%VENV%" python -m venv "%VENV%"
call "%VENV%\Scripts\activate.bat"
pip install --quiet -r djbot_src\requirements.txt

start "" http://127.0.0.1:%PORT%/
python -m uvicorn server:app --host 127.0.0.1 --port %PORT% --log-level warning
```

This is a starting draft for the plan, not a committed file — needs real Windows
testing (quoting with spaces in `%LOCALAPPDATA%\DJ Kyoko`, whether `where` behaves
as expected in all shells, whether the rubberband zip's internal folder structure
actually puts `rubberband.exe` where this script expects it) before it ships.

### SmartScreen / UAC

A downloaded, unsigned `.bat` or `.ps1` carries the Mark-of-the-Web and **will**
trigger a "Windows protected your PC" SmartScreen prompt on first run — this is
not avoidable without a paid code-signing certificate (and even then, a brand-new
cert has no reputation yet, so an EV cert is really what's needed for immediate
trust). The workaround for a friend is: SmartScreen dialog → "More info" → "Run
anyway", or right-click the file → Properties → check "Unblock" before running.
This should be called out explicitly in whatever instructions ship with the file —
don't let a friend think the app is broken/flagged as malware, it's just standard
Windows behavior for any unsigned downloaded script.

Batch files do **not** need UAC elevation for anything in this flow (venv, pip
install to a user-writable AppData folder, winget installs of user-scope packages)
— no admin prompt expected, but again, UNVERIFIED without a real Windows run.

### Bottom line for Windows

Genuinely doable, and the one hard blocker (rubberband) has a real fix via the
official prebuilt zip. The remaining risk is entirely "does this actually behave
the way Windows docs say it should" — batch scripting has enough quoting/PATH
footguns that this needs a real test pass on an actual Windows machine (or a VM)
before being handed to anyone. I'd treat this as a few hours of iteration once
there's a Windows box to test against, not a research gap.

---

## Part 2 — iPad / iPhone

### Native app: not feasible without a ground-up rewrite

Apple's App Store Review Guideline 2.5.2 explicitly prohibits apps from
downloading, installing, or executing code/binaries that weren't part of the
originally reviewed bundle, and blocks spawning arbitrary executables. This app's
entire architecture — spawn `yt-dlp`, `ffmpeg`, `rubberband`, `deno` as
subprocesses — is exactly the pattern this guideline exists to block. There is no
workaround; this isn't a packaging problem, it's a fundamental architecture
mismatch with iOS. A true native port would mean replacing every one of those
external tools with iOS-native equivalents (AVFoundation for audio manipulation,
a from-scratch YouTube-audio extraction approach, no deno/JS-challenge-solving
option at all) — that's a different, much larger project, not a packaging task.

### The realistic path: phone as a client, Mac (or PC) as the server

The app already IS a website (FastAPI + static HTML/JS frontend). The fix is
letting the phone/iPad reach that website instead of trying to run the whole
pipeline on-device.

**One required code/config change found:** `mac_app/DJ Kyoko.command` line 113
currently launches uvicorn with `--host 127.0.0.1` — this makes the server
unreachable from any other device, including on the same WiFi. Needs to become
`--host 0.0.0.0`.

**Everything else checks out already:**
- No CORS headers are configured, and none are needed — the frontend is served
  from the same FastAPI app as the API it calls (same origin), confirmed no
  `CORSMiddleware`/`allow_origins` in `server.py`.
- No hardcoded `127.0.0.1`/`localhost` references found in `static/index.html` —
  its `fetch()` calls use relative paths, so it will resolve correctly no matter
  what host/IP the page was loaded from.
- Range requests (needed for audio seeking/streaming) already work — confirmed
  live with a `curl -H "Range: ..."` test against the running server, got back a
  correct `206 Partial Content` with `Content-Range`. A phone streaming a 40MB mix
  over Tailscale will play progressively, not require a full download first.
- Mobile Safari's autoplay restriction (audio needs a user gesture before it can
  play) isn't a problem here — the player already requires a manual tap on
  play, it was never relying on autoplay.

**Two ways to reach it from the phone, easiest first:**
1. **Same WiFi network** — literally just `http://<Mac's LAN IP>:8934/` from the
   phone browser. Zero new setup, but only works when both devices are on the
   same network (e.g. at home).
2. **Tailscale (works from anywhere)** — Louis already has this fully configured
   per `claude-mobile-access/CLAUDE.md`: the Mac is reachable at
   `louiss-macbook-pro.tail7a0aeb.ts.net` (or IP `100.124.127.124`) from any
   device on his tailnet, which already includes his iPhone. Once the server
   binds to `0.0.0.0`, the URL from the phone becomes
   `http://louiss-macbook-pro.tail7a0aeb.ts.net:8934/` — no new Tailscale setup
   required, it's the same tailnet already used for the mobile Claude Code access.
   Add to iOS Home Screen via Safari's "Add to Home Screen" for an app-like icon.

**Security note:** binding to `0.0.0.0` opens port 8934 to the whole LAN, and (via
Tailscale) to every device on Louis's tailnet. Per the existing mobile-access
notes, that tailnet currently only has Louis's own Mac and iPhone on it — so this
is not exposing anything to the open internet, just worth stating explicitly
since it's a real behavior change from the current `127.0.0.1`-only binding.

### Bottom line for iPad/iPhone

No native app. The Tailscale-client approach costs one line of config change and
is otherwise already working today, verified live (Range requests, no CORS issue,
no hardcoded host refs). This is the same "keep the Mac as the always-on server"
pattern already established for driving Claude Code sessions from the phone —
it's a proven pattern in this exact setup, not a new concept.
