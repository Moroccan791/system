#!/usr/bin/env python3
"""Whop invariant checker: grade a finished clip against the BRAIN
(recipes/editing_brain.md), i.e. against the reference edits' measured
numbers - not against internal taste.

    python scripts/whop/check.py <video.mp4>

Reference yardsticks (from recipes/ref_vs_ours_teardown.md):
  * silences >0.25s:            refs 0 in 88s   (ours before: 13)
  * visual changes per 10s:      refs ~5-9      (ours before: 2.4)
  * longest unchanged stretch:   refs <= ~3s    (ours before: 20s)
  * first frame: a face, mid-speech - never a slate/title card
"""
from __future__ import annotations

import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, "scripts/whop")
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from clipper.ffmpeg import ffmpeg_exe  # noqa: E402


def main(path: str) -> int:
    ff = ffmpeg_exe()
    ok = True

    def verdict(name: str, good: bool, detail: str):
        nonlocal ok
        ok = ok and good
        print(f"[{'PASS' if good else 'FAIL'}] {name}: {detail}")

    # --- dead air -----------------------------------------------------
    r = subprocess.run([ff, "-i", path, "-af",
                        "silencedetect=noise=-35dB:d=0.25",
                        "-f", "null", "-"], capture_output=True, text=True)
    sils = []
    starts = [float(l.split("silence_start:")[1].strip())
              for l in r.stderr.splitlines() if "silence_start:" in l]
    durs = [float(l.split("silence_duration:")[1].strip())
            for l in r.stderr.splitlines() if "silence_duration:" in l]
    sils = list(zip(starts, durs))
    cap = cv2.VideoCapture(path)
    dur_s = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    body = [(s, d) for s, d in sils if s < dur_s - 1.6]  # endcard tail exempt
    verdict("dead air", len(body) == 0,
            f"{len(body)} silences >0.25s in {dur_s:.1f}s (refs: 0)")

    # --- visual change rate -------------------------------------------
    prev, changes, longest, cur = None, 0, 0.0, 0.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total_frames // 400)
    idx = 0
    last = None
    while True:
        okf, frame = cap.read()
        if not okf:
            break
        if idx % step == 0:
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                               (96, 170)).astype(np.float32)
            t = idx / (cap.get(cv2.CAP_PROP_FPS) or 30)
            if prev is not None:
                d = float(np.mean(np.abs(small - prev)))
                if d > 4.0:
                    changes += 1
                    longest = max(longest, cur)
                    cur = 0.0
                else:
                    cur = t - (last or t)
            prev = small
            last = t
        idx += 1
    longest = max(longest, cur)
    per10 = changes / max(dur_s, 0.1) * 10
    verdict("change rate", per10 >= 4.0,
            f"{per10:.1f} changes/10s (refs ~5-9), longest frozen "
            f"stretch {longest:.1f}s (refs <=3s)")
    verdict("no frozen stretch", longest <= 3.0, f"{longest:.1f}s")

    # --- first frame: face, not a slate -------------------------------
    cap.set(cv2.CAP_PROP_POS_FRAMES, 3)
    okf, frame = cap.read()
    cas = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cas.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                 1.1, 6, minSize=(60, 60)) if okf else []
    bright = float(frame.mean()) if okf else 0.0
    verdict("face-first open", len(faces) > 0 and bright > 25,
            f"faces in first frames: {len(faces)}, brightness {bright:.0f} "
            f"(a black slate reads <25)")

    print("WHOP INVARIANTS:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
