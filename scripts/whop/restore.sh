#!/usr/bin/env bash
# Restore the working tree after an arena workspace rollback.
#   bash scripts/whop/restore.sh
# The tracked work is always safe on origin; this rebuilds the
# untracked bits (venv, node modules, the concatenated footage).
set -u
cd /home/user/system
BRANCH=arena/5a6e6ca9-system
TIP=$(git ls-remote origin "refs/heads/$BRANCH" | cut -f1)
echo "remote tip: $TIP"
git fetch origin --prune >/dev/null 2>&1
git reset --hard "$TIP" && git log --oneline -1

# python env
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt pillow jsonschema
  .venv/bin/pip uninstall -y -q opencv-python opencv-contrib-python \
      opencv-python-headless opencv-contrib-python-headless 2>/dev/null
  .venv/bin/pip install -q --force-reinstall --no-deps opencv-contrib-python-headless==4.11.0.86
fi
.venv/bin/python -c "import cv2,numpy,imageio_ffmpeg,PIL,jsonschema;print('venv ok',cv2.__version__)"

# node modules for the renderer
if [ ! -d motion/node_modules ]; then (cd motion && npm ci >/dev/null 2>&1); fi
echo "node_modules: $([ -d motion/node_modules ] && echo ok || echo MISSING)"

# chromium runtime libs
if [ ! -f /tmp/al2023/lib/libnss3.so ]; then
  mkdir -p /tmp/al2023
  node -e "
    const fs=require('fs'),zlib=require('zlib'),cp=require('child_process');
    const b=fs.readFileSync('motion/node_modules/@sparticuz/chromium/bin/al2023.tar.br');
    fs.writeFileSync('/tmp/al2023/al2023.tar',zlib.brotliDecompressSync(b));
    cp.execFileSync('tar',['-xf','/tmp/al2023/al2023.tar','-C','/tmp/al2023']);"
fi
echo "chromium libs: $([ -f /tmp/al2023/lib/libnss3.so ] && echo ok || echo MISSING)"

# the concatenated source footage (4GB, gitignored, slow to rebuild)
if [ ! -f work/street/raw/street_full.mp4 ]; then
  mkdir -p work/street/raw_parts work/street/raw
  git fetch origin footage:refs/remotes/origin/footage >/dev/null 2>&1
  git archive origin/footage | tar -x -C work/street/raw_parts
  cd work/street
  printf "file 'raw_parts/part_%03d.mp4'\n" 0 1 2 3 4 5 6 7 > concat_list.txt
  FF=$(/home/user/system/.venv/bin/python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())")
  $FF -y -v error -f concat -safe 0 -i concat_list.txt -c copy raw/street_full.mp4
  cd /home/user/system
fi
echo "footage: $([ -f work/street/raw/street_full.mp4 ] && echo ok || echo MISSING)"
echo "restore done"
