#!/bin/bash
# Build + upload all 5 new sets after tracks are downloaded.
# Run AFTER download_tracks.sh completes.
# Usage: bash scripts/build_and_upload.sh 2>&1 | tee logs/build_and_upload.log

set -e
cd "$(dirname "$0")/.."
mkdir -p logs output

LOG="logs/build_and_upload.log"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  BUILD + UPLOAD PIPELINE  $(date)"
echo "══════════════════════════════════════════════════════"

BRAINS=(taleous bodzin bicep maceoplex benbohmer)

# ── Phase 1: Verify all tracks downloaded ─────────────────────────────────────
echo ""
echo "── Verifying downloads ─────────────────────────────────────────────────────"
MISSING=0
for BRAIN in "${BRAINS[@]}"; do
    python3 -c "
import importlib, sys
sys.path.insert(0, '.')
brain = importlib.import_module('brains.$BRAIN')
missing = [t for t in brain.TRACKS if not __import__('pathlib').Path(t['path']).exists()]
if missing:
    for t in missing:
        print(f'  MISSING: {t[\"path\"]}  ({t[\"label\"]})')
    sys.exit(1)
else:
    print(f'  $BRAIN: all {len(brain.TRACKS)} tracks present')
" || MISSING=$((MISSING+1))
done

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "  ERROR: $MISSING brain(s) have missing tracks. Run download_tracks.sh first."
    exit 1
fi
echo "  All tracks verified."

# ── Phase 2: Build each set ───────────────────────────────────────────────────
echo ""
echo "── Building sets ───────────────────────────────────────────────────────────"

for BRAIN in "${BRAINS[@]}"; do
    # Get output directory from brain
    OUTDIR=$(python3 -c "import importlib, sys; sys.path.insert(0, '.'); b = importlib.import_module(f'brains.$BRAIN'); print(f'output/{b.SET_NAME}')" 2>/dev/null)
    if [ -f "${OUTDIR}/FULL_SET.mp3" ]; then
        echo "  (already built) $BRAIN → $OUTDIR/FULL_SET.mp3"
        continue
    fi
    echo ""
    echo "  ── Building: $BRAIN ──"
    python build_set.py "$BRAIN" 2>&1 | tee "logs/${BRAIN}_build.log"
    echo "  ✓ $BRAIN built"
done

# ── Phase 3: Upload each set to Mixcloud ──────────────────────────────────────
echo ""
echo "── Uploading to Mixcloud ───────────────────────────────────────────────────"

for BRAIN in "${BRAINS[@]}"; do
    echo ""
    echo "  ── Uploading: $BRAIN ──"
    python scripts/mixcloud_upload.py "$BRAIN" 2>&1 | tee "logs/${BRAIN}_upload.log" || {
        echo "  ✗ $BRAIN upload failed — check logs/${BRAIN}_upload.log"
        exit 1
    }
    echo "  ✓ $BRAIN uploaded"
    echo "  Waiting 60s for Mixcloud rate limit..."
    sleep 60
done

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ALL DONE  $(date)"
echo "  Check: https://www.mixcloud.com/louis-lapat/"
echo "══════════════════════════════════════════════════════"
