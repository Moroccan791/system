#!/bin/bash
# The two podcast-reel tutorials only, sequential (moonshine peaks ~3 GB RAM).
# The time-remap montage tutorial is excluded on the user's say-so.
cd /home/user/system
for f in tutorials/viral_podcast_reels_fast.mp4 tutorials/viral_podcast_reel_editing.mp4; do
  echo "=== transcribing $f ==="
  python3 -m clipper transcribe "$f" --asr moonshine 2>&1 | tail -5
done
echo "=== all done ==="
