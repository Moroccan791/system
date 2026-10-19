#!/bin/bash
# WHOP FIX — apply on arena/5a6e6ca9-system (run from repo root)
# Fixes: orphan gap_break, transitions, paper lock
set -e
# 1. orphan fix
echo "Patching clipper/captions/cues.py (gap 0.45->0.60)..."
patch -p1 < "WHOP PRO FIX - APPLY TO 5a6e6ca/FIXES_READY/gap_break_fix.patch" && echo "✓ cues.py" || echo "skip cues.py (already patched?)"

# 2. transitions -> cut only
echo "Patching transitions to cut only..."
patch -p1 < "WHOP PRO FIX - APPLY TO 5a6e6ca/FIXES_READY/transitions_fix.patch" && echo "✓ transitions" || echo "skip transitions"

# 3. quick verify
echo ""
echo "=== VERIFY ==="
grep -n "gap_break" clipper/captions/cues.py | head
echo "---transitions---"
cat motion/themes/whop.json | grep -A2 transitionOrder

echo ""
echo "Next: re-render post5/6/7 (post5 is 18s -> extend to 28s)"
echo "  python -m clipper edit street_you_grew_up_on --ids #post5 --plan-only"
echo "  python -m clipper captions work/.../edits/...mp4 --plan work/.../edits/...plan.json --punch"
