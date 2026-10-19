#!/bin/bash
# One-time: convert woff2 fonts to ttf so ffmpeg libass fontsdir can find them
# Requires: pip install fonttools brotli
set -e
cd "$(dirname "$0")/../../assets/fonts" 2>/dev/null || cd "assets/fonts"
echo "Converting woff2 → ttf in $(pwd)"
for w in *.woff2; do
  [ -e "$w" ] || continue
  base="${w%.woff2}"
  if [ -f "$base.ttf" ]; then echo "SKIP $base.ttf exists"; continue; fi
  echo "→ $w → $base.ttf"
  python3 -c "
from fontTools.ttLib import TTFont
f=TTFont('$w')
f.flavor=None
f.save('$base.ttf')
print('OK $base.ttf')
" 2>&1 || echo "FAIL $w — install fonttools: pip install fonttools brotli"
done
echo "Done. ls *.ttf:"
ls -lh *.ttf | head -20
echo "Next: python -m clipper doctor"
