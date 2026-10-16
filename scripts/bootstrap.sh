#!/usr/bin/env bash
# One-command sandbox rebuild after a reset wipes .venv/ and models/.
# Everything here is idempotent; safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

MODEL=assets/models/face_detection_yunet_2023mar.onnx
if [ ! -f "$MODEL" ]; then
  echo "restoring YuNet face model from opencv_zoo..."
  tmp=$(mktemp -d)
  curl -sL https://codeload.github.com/opencv/opencv_zoo/tar.gz/refs/heads/main -o "$tmp/zoo.tgz"
  tar -xzf "$tmp/zoo.tgz" -C "$tmp" --wildcards "*/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
  mkdir -p assets/models
  cp "$tmp"/opencv_zoo-main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx "$MODEL"
  rm -rf "$tmp"
fi

.venv/bin/python -c "import moonshine_cpp, cv2, silero_vad; print('bootstrap ok')"
