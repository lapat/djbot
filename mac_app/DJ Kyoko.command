#!/bin/bash
# DJ Kyoko — double-click launcher for Mac
# Builds automatic beat-matched DJ mixes from free-text requests, with a
# live web UI showing real progress. Closing this Terminal window stops it.
set -u
cd "$(dirname "$0")" || exit 1
SRC="$(pwd)/djbot_src"
APP_SUPPORT="$HOME/Library/Application Support/DJ Kyoko"
mkdir -p "$APP_SUPPORT"
VENV="$APP_SUPPORT/venv"
# Downloads/output/beatgrid-cache must NOT live inside the .app bundle:
# macOS App Translocation runs a downloaded/quarantined .app from a
# randomized read-only copy of itself, so any write under the bundle fails
# with "[Errno 30] Read-only file system" the moment a real job downloads a
# track. Point job data at Application Support instead (always writable).
export DJBOT_DATA_DIR="$APP_SUPPORT/data"
mkdir -p "$DJBOT_DATA_DIR"
REQ_HASH_FILE="$APP_SUPPORT/.reqs_installed_hash"
PORT=8934

# Bump this — and MAC_APP_VERSION in djbot-gallery/app.py — every time a new
# signed build ships via mac_app/build_signed_app.sh.
LOCAL_APP_VERSION="2026-08-19-outrobars-fix-v1"
GALLERY_URL="https://djbot-gallery-production.up.railway.app"

# ── Auto-update ────────────────────────────────────────────────────────────
# Runs before anything else so friends always get the latest build without
# having to notice/re-download manually. Replaces the WHOLE .app bundle as
# one atomic swap — never patches files inside the currently-running bundle,
# since that would invalidate its notarized signature and bring back the
# exact Gatekeeper warning this app was signed to avoid. Safe to skip on any
# failure (offline, permissions, etc.) — never blocks a normal launch.
# cwd is already ".../DJ Kyoko.app/Contents/Resources" thanks to the `cd`
# above, so resolve relative to the CURRENT directory, not $0 again — $0
# still holds whatever (possibly relative) path was used to invoke this
# script, and re-deriving from it here after cwd has already changed
# produces a broken double-nested path.
APP_BUNDLE="$(cd ../.. && pwd)"
if [[ "$APP_BUNDLE" == *.app ]]; then
  LATEST_VERSION="$(curl -s -m 5 "$GALLERY_URL/api/app-version" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('mac_version',''))" 2>/dev/null)"
  if [ -n "$LATEST_VERSION" ] && [ "$LATEST_VERSION" != "$LOCAL_APP_VERSION" ]; then
    echo "A new version of DJ Kyoko is available ($LATEST_VERSION) — updating..."
    TMP_ZIP="$(mktemp -t djkyoko-update).zip"
    TMP_EXTRACT="$(mktemp -d -t djkyoko-update-extract)"
    if curl -sL -o "$TMP_ZIP" "$GALLERY_URL/download/mac" \
       && unzip -oq "$TMP_ZIP" -d "$TMP_EXTRACT" \
       && [ -d "$TMP_EXTRACT/DJ Kyoko.app" ]; then
      OLD_BACKUP="${APP_BUNDLE}.old-$$"
      if mv "$APP_BUNDLE" "$OLD_BACKUP" 2>/dev/null && mv "$TMP_EXTRACT/DJ Kyoko.app" "$APP_BUNDLE" 2>/dev/null; then
        rm -rf "$OLD_BACKUP" "$TMP_ZIP" "$TMP_EXTRACT"
        echo "Updated — relaunching..."
        open "$APP_BUNDLE"
        exit 0
      else
        echo "Update install failed (permissions?) — continuing with the current version."
        [ -d "$OLD_BACKUP" ] && mv "$OLD_BACKUP" "$APP_BUNDLE" 2>/dev/null
        rm -rf "$TMP_ZIP" "$TMP_EXTRACT"
      fi
    else
      echo "Update download failed — continuing with the current version."
      rm -rf "$TMP_ZIP" "$TMP_EXTRACT"
    fi
  fi
fi

osa_ok() {
  DJBOT_MSG="$1" osascript <<'EOF'
on run
  set msg to system attribute "DJBOT_MSG"
  display dialog msg buttons {"OK"} default button 1 with title "DJ Kyoko"
end run
EOF
}

echo "========================================"
echo "   DJ Kyoko - Automatic Mix Builder"
echo "========================================"
echo

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi
if ! command -v brew >/dev/null 2>&1; then
  osa_ok "DJ Kyoko needs Homebrew (a standard Mac package installer) to set up ffmpeg and rubberband. Click OK, then this window will ask for your Mac password to install it."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi
if ! command -v brew >/dev/null 2>&1; then
  osa_ok "Homebrew install didn't finish. Please re-run this file, or ask Louis for help."
  exit 1
fi

# 2. ffmpeg / rubberband / deno (deno solves YouTube's JS signature
#    challenges for yt-dlp — without it, downloads fail with 403s)
for pkg in ffmpeg rubberband deno; do
  if ! command -v "$pkg" >/dev/null 2>&1; then
    echo "Installing $pkg (first run only)..."
    brew install "$pkg"
  fi
done

# 3. python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing python3 (first run only)..."
  brew install python@3.11
fi

# 4. venv + deps
if [ ! -d "$VENV" ]; then
  echo "Setting up DJ Kyoko (first run only, a few minutes)..."
  python3 -m venv "$VENV"
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"

REQ_HASH=$(shasum "$SRC/requirements.txt" | awk '{print $1}')
if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat "$REQ_HASH_FILE" 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "Installing dependencies (first run only, this can take several minutes)..."
  pip install --quiet --upgrade pip
  INSTALL_OK=0
  for attempt in 1 2 3; do
    if pip install --quiet --retries 10 --timeout 60 -r "$SRC/requirements.txt"; then
      INSTALL_OK=1
      break
    fi
    echo "Dependency install attempt $attempt failed (likely a network hiccup) — retrying in 15s..."
    sleep 15
  done
  if [ "$INSTALL_OK" -ne 1 ]; then
    osa_ok "Dependency install failed after 3 attempts, likely a network problem. Check your internet connection and re-run this file."
    exit 1
  fi
  echo "$REQ_HASH" > "$REQ_HASH_FILE"
fi

# 5. Launch the web UI
echo
echo "Starting DJ Kyoko..."
export DJBOT_APP_SUPPORT="$APP_SUPPORT"

# Bonjour/mDNS local hostname (e.g. louiss-macbook-pro.local) — every Mac
# already broadcasts this, no setup needed, and it also works from a phone/
# iPad on the same WiFi (not just this machine), unlike 127.0.0.1.
LOCAL_HOST="$(scutil --get LocalHostName 2>/dev/null || hostname -s).local"
APP_URL="http://${LOCAL_HOST}:$PORT"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

(
  for i in $(seq 1 60); do
    if curl -s -m 1 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      if [ -x "$CHROME_APP" ]; then
        # --app= opens a chromeless window (no tabs/address bar) — reads as
        # a real application instead of "a browser tab pointed at an IP."
        "$CHROME_APP" --app="$APP_URL" --window-size=1280,880 >/dev/null 2>&1 &
      else
        open "$APP_URL"
      fi
      exit 0
    fi
    sleep 0.5
  done
) &

echo "Opening DJ Kyoko at $APP_URL ..."
echo "(Leave this window open while you use DJ Kyoko — closing it stops the app.)"
echo "(Also reachable from your phone/iPad on the same WiFi at $APP_URL, or over Tailscale from anywhere — see CROSS_PLATFORM_PLAN.md.)"
echo

cd "$SRC/webapp"
exec python -m uvicorn server:app --host 0.0.0.0 --port "$PORT" --log-level warning
