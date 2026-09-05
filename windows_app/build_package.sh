#!/bin/bash
# Builds "DJ Kyoko-package.zip" from windows_app/djbot_src — the Windows
# distributable. Runs on the Mac dev machine (no code-signing/notarization
# needed for Windows, unlike mac_app/build_signed_app.sh's Apple pipeline —
# Windows friends just unzip and run DJ Kyoko.bat).
#
# Structure matches the existing hand-built "DJ Kyoko Windows.zip" exactly
# (confirmed via `unzip -l` 2026-09-05): flat root files (DJ Kyoko.ps1,
# DJ Kyoko.bat) plus djbot_src/ as a subdirectory tree. djbot_src/webapp/
# .shared_key is deliberately included — it's a spend-capped proxy relay
# token, not a raw API key (see mac_app/build_signed_app.sh's identical
# handling), and Windows friends need it the same way Mac friends do.
#
# Output: windows_app/DJ Kyoko-package.zip — verify it, THEN copy it over
# static/downloads/DJ Kyoko Windows.zip in djbot-gallery as a separate step
# (this script never touches djbot-gallery itself).
set -euo pipefail
cd "$(dirname "$0")"

# Pre-flight staleness gate (2026-09-05) — same as mac_app/build_signed_app.sh.
# Refuses to package a djbot_src that's drifted from source rather than
# relying on someone remembering to run check_stale.py first.
if ! python3 "../mac_app/check_stale.py" --target windows; then
  echo
  echo "Refusing to package: windows_app/djbot_src is stale (see above). Sync it first."
  exit 1
fi

OUT="DJ Kyoko-package.zip"
OUT_ABS="$(pwd)/$OUT"
BUILD_DIR="$(mktemp -d)"
STAGE="$BUILD_DIR/stage"
mkdir -p "$STAGE"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "== 1. Staging files =="
cp "DJ Kyoko.ps1" "$STAGE/DJ Kyoko.ps1"
cp "DJ Kyoko.bat" "$STAGE/DJ Kyoko.bat"
[ -f "README_FOR_FRIEND_WINDOWS.txt" ] && cp "README_FOR_FRIEND_WINDOWS.txt" "$STAGE/README_FOR_FRIEND_WINDOWS.txt"
rsync -a --exclude='downloads/' --exclude='output/' --exclude='__pycache__/' --exclude='*.pyc' \
  "djbot_src/" "$STAGE/djbot_src/"

echo "== 2. Packaging =="
rm -f "$OUT_ABS"
( cd "$STAGE" && zip -rq "$OUT_ABS" . )

echo
echo "Done: $OUT_ABS"
