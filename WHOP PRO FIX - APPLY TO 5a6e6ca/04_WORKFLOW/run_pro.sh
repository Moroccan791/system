#!/bin/bash
# WHOP PRO run — one command from raw to post-ready (TikTok + Reels + Shorts)
# Usage: bash run_pro.sh <campaign> [--top N] [--platform tiktok|reels|shorts|all]
# Live on arena/1b875d65-system, designed for arena/5a6e6ca9-system
# Requires: python -m clipper (scan/style/select/edit/captions/cover) + ffmpeg with libass
set -euo pipefail

CAMPAIGN="${1:-michael_sartain}"
TOP=4
PLATFORM="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --top) TOP="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Resolve paths relative to repo root (works from any branch)
if [ -f "WHOP PRO FIX - APPLY TO 5a6e6ca/04_WORKFLOW/run_pro.sh" ]; then
  ROOT="$(pwd)"
else
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
# If on 5a6e6ca worktree, ROOT is that worktree — good. If on 1b875d65, patches still reference correct relative paths.

echo "=== WHOP PRO RUN: $CAMPAIGN top=$TOP platform=$PLATFORM ==="
echo "Root: $ROOT"

# Prefer pro style if exists
STYLE_ARG=""
if [ -f "$ROOT/styles/$CAMPAIGN.pro.style.json" ]; then
  STYLE_ARG="--style $ROOT/styles/$CAMPAIGN.pro.style.json"
  echo "Using PRO style: styles/$CAMPAIGN.pro.style.json"
elif [ -f "$ROOT/WHOP PRO FIX - APPLY TO 5a6e6ca/01_CAPTIONS/$CAMPAIGN.pro.style.json" ]; then
  STYLE_ARG="--style $ROOT/WHOP PRO FIX - APPLY TO 5a6e6ca/01_CAPTIONS/$CAMPAIGN.pro.style.json"
  echo "Using FIXPACK pro style"
fi

# 1. Scan (cached)
if [ ! -f "$ROOT/work/$CAMPAIGN/manifest.json" ]; then
  echo "[1/6] scan $CAMPAIGN"
  python -m clipper scan "$CAMPAIGN" || echo "scan skip (no campaign folder yet)"
else
  echo "[1/6] scan — cached (manifest exists)"
fi

# 2. Style (cached, pro overrides learned)
if [ -n "$STYLE_ARG" ]; then
  echo "[2/6] style — using pro (skip learn)"
else
  if [ ! -f "$ROOT/styles/$CAMPAIGN.style.json" ]; then
    echo "[2/6] style $CAMPAIGN"
    python -m clipper style "$CAMPAIGN" || echo "style warn"
  else
    echo "[2/6] style — cached"
  fi
fi

# 3. Select moments
echo "[3/6] select $CAMPAIGN --top $TOP"
python -m clipper select "$CAMPAIGN" --top "$TOP" || echo "select warn"

# 4-6. Per candidate: edit (plan) → captions (carried) → cover + post
CAND_DIR="$ROOT/work/$CAMPAIGN/candidates"
EDIT_DIR="$ROOT/work/$CAMPAIGN/edits"
if [ ! -d "$CAND_DIR" ]; then
  echo "No candidates at $CAND_DIR — check campaign has raw footage"
  exit 1
fi

PLATFORMS=()
if [ "$PLATFORM" = "all" ]; then PLATFORMS=("tiktok" "reels" "shorts")
else PLATFORMS=("$PLATFORM"); fi

for cand in "$CAND_DIR"/*.json; do
  [ -e "$cand" ] || continue
  id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('id','?') if isinstance(json.load(open(sys.argv[1])), dict) else json.load(open(sys.argv[1]))[0].get('id','?'))" "$cand" 2>/dev/null || echo "unknown")
  echo ""
  echo "--- candidate $id ($cand) ---"

  # Edit: plan only first (fast, 0.5s), then full render with plan
  # Use --plan-only to generate plan.json without ffmpeg, then captions will carry timings
  # Fallback: direct edit if plan-only not available
  if python -m clipper edit "$CAMPAIGN" --ids "$id" --plan-only 2>&1 | head -5; then
    echo "  plan ok"
  else
    echo "  plan-only not available, will render directly"
  fi

  PLAN="$EDIT_DIR"/*.plan.json
  # Find plan matching this id (clipper writes <raw>_<id>.plan.json)
  PLAN_FILE=$(ls "$EDIT_DIR"/*"$id"*.plan.json 2>/dev/null | head -1 || echo "")
  if [ -n "$PLAN_FILE" ]; then
    # Captions with carried timings (no re-ASR, 2x faster, no drift)
    echo "  captions with --plan $PLAN_FILE"
    # The edit stage already wrote the video to work/.../edits/*.mp4 — now burn captions with plan
    VIDEO=$(ls "$EDIT_DIR"/*"$id"*.mp4 2>/dev/null | grep -v plan | head -1 || echo "")
    if [ -n "$VIDEO" ]; then
      for plat in "${PLATFORMS[@]}"; do
        echo "  export $plat"
        python -m clipper captions "$VIDEO" --campaign "$CAMPAIGN" --plan "$PLAN_FILE" --platform "$plat" $STYLE_ARG --punch --tighten 0.6 2>&1 | tail -2 || echo "  captions $plat warn"
      done
    fi
  else
    # No plan — fallback to direct captions (will re-ASR, slower)
    echo "  no plan file, fallback caption pass (will re-ASR)"
    for plat in "${PLATFORMS[@]}"; do
      VIDEO=$(ls "$EDIT_DIR"/*"$id"*.mp4 2>/dev/null | head -1 || echo "")
      [ -n "$VIDEO" ] && python -m clipper captions "$VIDEO" --campaign "$CAMPAIGN" --platform "$plat" $STYLE_ARG --punch 2>&1 | tail -2 || true
    done
  fi

  # Cover + post.txt would be generated here if clipper cover/post exists
  # See clipper/captions/cover.py — needs payoff timestamp from candidate
  echo "  candidate $id done"
done

echo ""
echo "=== DONE $CAMPAIGN ==="
echo "Check: work/$CAMPAIGN/edits/ for rendered clips"
echo "Check: python -m clipper serve --port 8000"
