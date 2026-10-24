#!/usr/bin/env bash
# Rebuild the working tree after an arena workspace rollback.
#
#     bash scripts/whop/restore.sh              # code + env + the episode
#     bash scripts/whop/restore.sh --no-footage # skip the 680 MB download
#     bash scripts/whop/restore.sh --env-only   # just the interpreter
#
# What survives a rollback: everything tracked, which is on origin. What does
# not: the venv, node_modules, the chromium libs, and work/ — the raw footage
# and every transcript.
#
# Two bugs were fixed here. It used to reset to a hardcoded branch name
# (`arena/5a6e6ca9-system`), which is a stale branch that no longer receives
# commits: running it threw away the current work and left the tree at an old
# tip. The branch is now whatever you are on. And it assumed the venv was
# called `.venv`, when it is called `venv` in this sandbox — so it rebuilt a
# second environment beside an existing one and the pipeline kept using
# whichever it found first.
set -u
cd "$(dirname "$0")/../.." || exit 1
ROOT=$(pwd)

WITH_FOOTAGE=1
ENV_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-footage) WITH_FOOTAGE=0 ;;
    --env-only)   ENV_ONLY=1; WITH_FOOTAGE=0 ;;
  esac
done

# ---- 1. the code -----------------------------------------------------------
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "HEAD" ]; then
  echo "refusing to run on a detached HEAD — check out the session branch first"
  exit 1
fi
echo "branch: $BRANCH"
if [ "$ENV_ONLY" -eq 0 ]; then
  TIP=$(git ls-remote origin "refs/heads/$BRANCH" | cut -f1)
  echo "remote tip: ${TIP:-<none>}"
  if [ -n "${TIP:-}" ]; then
    git fetch origin --prune >/dev/null 2>&1
    git reset --hard "$TIP" >/dev/null && git log --oneline -1
  fi
fi

# ---- 2. the interpreter ----------------------------------------------------
# Whichever environment already exists. `.venv` is the convention this repo was
# written with; `venv` is what the sandbox creates. Both are fine — the scripts
# use sys.executable, so the name does not matter, only that one exists.
PYDIR=""
for d in .venv venv; do
  if [ -x "$d/bin/python" ]; then PYDIR="$d"; break; fi
done
if [ -z "$PYDIR" ]; then
  PYDIR=.venv
  echo "creating $PYDIR"
  python3 -m venv "$PYDIR" || exit 1
fi
echo "interpreter: $PYDIR/bin/python"
"$PYDIR/bin/pip" install -q --upgrade pip >/dev/null 2>&1
"$PYDIR/bin/pip" install -q -r requirements.txt >/dev/null 2>&1
"$PYDIR/bin/pip" install -q pillow jsonschema >/dev/null 2>&1
"$PYDIR/bin/python" - <<'EOF'
import importlib, sys
need = {"numpy": "numpy", "PIL": "pillow", "cv2": "opencv", "jsonschema": "jsonschema"}
missing = []
for mod, pip_name in need.items():
    try:
        importlib.import_module(mod)
    except Exception:
        missing.append(pip_name)
if missing:
    print("venv INCOMPLETE, missing: " + ", ".join(missing))
    sys.exit(1)
import cv2
print("venv ok, cv2", cv2.__version__)
EOF
[ $? -ne 0 ] && echo "  fix: $PYDIR/bin/pip install -r requirements.txt"

# ---- 3. the renderer -------------------------------------------------------
if [ "$ENV_ONLY" -eq 0 ]; then
  if [ ! -d motion/node_modules ]; then
    (cd motion && npm ci >/dev/null 2>&1)
  fi
  echo "node_modules: $([ -d motion/node_modules ] && echo ok || echo MISSING)"

  # chromium runtime libs; the renderer only needs these when it is present
  if [ ! -f /tmp/al2023/lib/libnss3.so ] && [ -f motion/node_modules/@sparticuz/chromium/bin/al2023.tar.br ]; then
    mkdir -p /tmp/al2023
    node -e "
      const fs=require('fs'),zlib=require('zlib'),cp=require('child_process');
      const b=fs.readFileSync('motion/node_modules/@sparticuz/chromium/bin/al2023.tar.br');
      fs.writeFileSync('/tmp/al2023/al2023.tar',zlib.brotliDecompressSync(b));
      cp.execFileSync('tar',['-xf','/tmp/al2023/al2023.tar','-C','/tmp/al2023']);" \
      && echo "chromium libs: ok" || echo "chromium libs: MISSING"
  else
    echo "chromium libs: $([ -f /tmp/al2023/lib/libnss3.so ] && echo ok || echo 'absent (renderer only)')"
  fi
fi

# ---- 4. the footage --------------------------------------------------------
if [ "$WITH_FOOTAGE" -eq 1 ]; then
  if [ -f work/street/raw/street_full.mp4 ]; then
    echo "footage: already here"
  else
    mkdir -p work/street/raw_parts work/street/raw
    # blobless and shallow: the branch is 680 MB of video and only the parts
    # are needed, so a full fetch is most of the wait for none of the benefit
    git fetch --filter=blob:none --depth=1 origin \
        footage:refs/remotes/origin/footage >/dev/null 2>&1
    if git archive refs/remotes/origin/footage | tar -x -C work/street/raw_parts 2>/dev/null \
       && [ -n "$(ls -A work/street/raw_parts 2>/dev/null)" ]; then
      printf "file 'raw_parts/part_%03d.mp4'\n" 0 1 2 3 4 5 6 7 > work/street/concat_list.txt
      FF=$("$PYDIR/bin/python" -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())")
      ( cd work/street && "$FF" -y -v error -f concat -safe 0 \
          -i concat_list.txt -c copy raw/street_full.mp4 )
      echo "footage: joined $(du -h work/street/raw/street_full.mp4 2>/dev/null | cut -f1)"
    else
      echo "footage: could not read the footage branch"
      echo "  the release copy is the fallback:"
      echo "  python scripts/whop/doctor.py --fetch part_000.mp4"
    fi
  fi
fi

# ---- 5. what a reset always takes with it ----------------------------------
cat <<'EOF'

Transcripts are NOT restorable from git — work/ is gitignored, so the ASR
output goes with it. Re-cut them from the audio:

    python scripts/whop/transcribe_episode.py <episode.mp4>
    (or push a request to .github/workflows/asr-words.yml)

Then ask what is missing:

    python scripts/whop/doctor.py --post post6
EOF
echo "restore done"
