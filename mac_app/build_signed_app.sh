#!/bin/bash
# Builds, signs, and notarizes "DJ Kyoko.app" from mac_app/djbot_src.
#
# One-time setup already done (2026-08-19), do not repeat unless the
# certificate expires (2031/08/19) or is revoked:
#   - "Developer ID Application: Coinflash, LLC (Q2VTH3TP6E)" imported into
#     the login keychain (both cert + matching private key).
#   - notarytool credentials stored under keychain profile "djkyoko"
#     (xcrun notarytool store-credentials "djkyoko" --apple-id ... --team-id ...)
#
# Output: mac_app/DJ Kyoko-signed.zip — a notarized, stapled .app ready to
# distribute. Verified to pass Gatekeeper even with a real browser-download
# quarantine flag set (spctl -a -vv reports "accepted, source=Notarized
# Developer ID"), AND verified by actually running it (not just checking the
# signature) — see README_FOR_FRIEND.txt for the one-time system dialog this
# triggers on first launch (macOS asking permission for the app to run a
# command via `do shell script`) — normal, one-time, not a Gatekeeper warning.
#
# The wrapper deliberately uses `do shell script "open ..."` instead of
# `tell application "Terminal" to do script ...` — the latter requires a
# separate "Automation" permission (System Settings > Privacy & Security >
# Automation) that isn't granted by default and fails with a silent,
# permanent "-1743 Not authorized to send Apple events to Terminal" error
# with no way to grant it from inside the error dialog itself. `open` on the
# .command file just uses normal LaunchServices file-opening, which only
# needs the one-time do-shell-script prompt, not Automation permission.
set -euo pipefail
cd "$(dirname "$0")"

IDENTITY="Developer ID Application: Coinflash, LLC (Q2VTH3TP6E)"
NOTARY_PROFILE="djkyoko"
BUILD_DIR="$(mktemp -d)"
APP="$BUILD_DIR/DJ Kyoko.app"

trap 'rm -rf "$BUILD_DIR"' EXIT

echo "== 1. Building app shell =="
cat > "$BUILD_DIR/wrapper.applescript" << 'APPLESCRIPT_EOF'
on run
	set scriptPath to (POSIX path of (path to me)) & "Contents/Resources/DJ Kyoko.command"
	do shell script "open " & quoted form of scriptPath
end run
APPLESCRIPT_EOF
osacompile -o "$APP" "$BUILD_DIR/wrapper.applescript"

echo "== 2. Copying resources (excluding job output/downloads bloat) =="
rsync -a --exclude='output/' --exclude='downloads/' --exclude='__pycache__/' --exclude='*.pyc' \
  "djbot_src/" "$APP/Contents/Resources/djbot_src/"
cp "DJ Kyoko.command" "$APP/Contents/Resources/DJ Kyoko.command"
cp "README_FOR_FRIEND.txt" "$APP/Contents/Resources/README_FOR_FRIEND.txt"
chmod +x "$APP/Contents/Resources/DJ Kyoko.command"

echo "== 3. Setting bundle metadata =="
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.coinflash.djkyoko" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.0" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 1" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 11.0" "$APP/Contents/Info.plist" 2>/dev/null || true

echo "== 4. Code signing (hardened runtime) =="
find "$APP" -name "*.cstemp*" -delete 2>/dev/null || true
codesign --deep --force --options runtime --timestamp --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "== 5. Submitting for notarization (can take a few minutes) =="
ditto -c -k --keepParent "$APP" "$BUILD_DIR/submit.zip"
xcrun notarytool submit "$BUILD_DIR/submit.zip" --keychain-profile "$NOTARY_PROFILE" --wait

echo "== 6. Stapling ticket =="
xcrun stapler staple "$APP"
spctl -a -vv "$APP"

echo "== 7. Packaging final distributable =="
rm -f "DJ Kyoko-signed.zip"
ditto -c -k --keepParent "$APP" "DJ Kyoko-signed.zip"

echo
echo "Done: $(pwd)/DJ Kyoko-signed.zip"
