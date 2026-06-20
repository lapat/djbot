#!/bin/bash
# Download all tracks needed for the 5 new sets.
# Usage: bash scripts/download_tracks.sh

set -e
cd "$(dirname "$0")/.."
mkdir -p downloads/new_tracks logs

LOG="logs/download_tracks.log"
exec > >(tee -a "$LOG") 2>&1

echo ""
echo "══════════════════════════════════════════════"
echo "  DOWNLOADING TRACKS  $(date)"
echo "══════════════════════════════════════════════"

download_track() {
    local VID="$1"
    local OUT="downloads/new_tracks/${VID}.mp3"
    if [ -f "$OUT" ]; then
        echo "  (cached) $VID"
        return 0
    fi
    echo "  Downloading $VID ..."
    yt-dlp -x --audio-format mp3 --audio-quality 0 \
        --match-filter "duration > 300" \
        -o "downloads/new_tracks/%(id)s.%(ext)s" \
        --no-playlist \
        "https://www.youtube.com/watch?v=${VID}" 2>&1 | grep -E "(Download|ERROR|already|Destination|duration)" || true
    if [ -f "$OUT" ]; then
        SIZE=$(du -h "$OUT" | cut -f1)
        echo "  ✓ $VID  ($SIZE)"
    else
        echo "  ✗ $VID — FAILED (check log)"
    fi
}

# All 42 unique video IDs needed
VIDEOS=(
    # taleous (Afterlife/Tale Of Us)
    5LHyicZB2-E JaDLh6XRL2o tCc7plT1Wi0 ujgBWFUcYdI d-sLhOJ739c
    QYXhmDpKAig 1LnLTDWHiUg Ze5cAbbo7W0 RTfgvVxVdVE LIOL2AoE40M 8bkUCXbjfFs

    # bodzin (Stephan Bodzin)
    KTdpVohzM3s bTFdoMfTd4Y 2x_rGWJYWAs T7hcAL4Cktc 8hrOW_psDlc
    AaxFuXpcQmE vR8lgfjCADc KNIuarCkhe8

    # bicep
    KEIr-44bCj4 1VVE9k0TzSM O5Osa4sJEro DPm9RVpwOLQ myDq5LwbxuU
    QV58Z5Xsy4o eZWY0YtOAOk obe02lLwyps ZsxrCuH0Ae0

    # maceoplex (Maceo Plex)
    ZDUxus3eSsE 9Dcgngu88XU b9YakgsJJgI oed40p0t1aE qTf07KDSLc4
    3ErLuLJmrtY YpnF6zHgF5w 3JkpYmCn9ks

    # benbohmer (Ben Böhmer)
    9E2pX27Exkc xF5PzY4b3eQ upm7qgomnp0 _jWp5RpEjt0 W84W0YGxJK4
    WGIbLbLcNns ums8n8tTL6M
)

echo "  Total: ${#VIDEOS[@]} tracks (1 already cached)"
echo ""

for VID in "${VIDEOS[@]}"; do
    download_track "$VID"
done

echo ""
echo "══════════════════════════════════════════════"
echo "  Download phase complete  $(date)"
CACHED=$(ls downloads/new_tracks/*.mp3 2>/dev/null | wc -l)
echo "  Files in downloads/new_tracks: $CACHED"
echo "══════════════════════════════════════════════"
