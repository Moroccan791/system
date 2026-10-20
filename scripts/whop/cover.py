#!/usr/bin/env python3
"""Pick the cover frame instead of taking whatever is at 2.26 s.

The cover is the only frame most people will ever see: it is what the grid
shows, what a share preview uses, and on a profile it is the thumbnail of the
whole account. It was previously "0.30 s after a word we happened to like",
which is a guess.

Scoring, in order of what actually ruins a cover:

    sharpness   a soft frame reads as a cheap clip before anything else lands
    face        present, and large enough to recognise at 200 px wide
    exposure    not blown, not crushed - the caption has to sit on it too

Blink detection needs eye landmarks; the detector we have gives five points,
which is not enough to tell open from closed. Rather than fake it, the scorer
takes several candidates and prefers the sharpest of the top band, which
sidesteps most blinks without pretending to detect them.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parents[2] / "assets" / "models" / "face_detection_yunet_2023mar.onnx"

DEFAULTS = {"step": 0.2, "w_sharp": 0.55, "w_face": 0.30, "w_exposure": 0.15,
            "sharp_ref": 900.0, "area_ref": 0.22, "exposure_ref": 110.0}


def score_frame(frame: np.ndarray, face: tuple[float, float, float, float] | None,
                cfg: dict | None = None) -> dict:
    c = {**DEFAULTS, **(cfg or {})}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    area = 0.0 if face is None else (float(face[2]) * float(face[3])) / (w * h)
    mean = float(gray.mean())
    s_sharp = min(1.0, sharp / float(c["sharp_ref"]))
    s_face = min(1.0, area / float(c["area_ref"]))
    s_exp = max(0.0, 1.0 - abs(mean - float(c["exposure_ref"])) / float(c["exposure_ref"]))
    total = (float(c["w_sharp"]) * s_sharp + float(c["w_face"]) * s_face
             + float(c["w_exposure"]) * s_exp)
    return {"score": round(total, 4), "sharpness": round(sharp, 1),
            "face_area": round(area, 4), "mean": round(mean, 1),
            "parts": {"sharp": round(s_sharp, 3), "face": round(s_face, 3),
                      "exposure": round(s_exp, 3)}}


def best_frame(video: Path, *, start: float = 1.0, end: float | None = None,
               cfg: dict | None = None, model: Path = MODEL) -> dict:
    """Scan the clip and return the frame that will read best in a grid."""
    c = {**DEFAULTS, **(cfg or {})}
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
    end = total if end is None else min(end, total)
    det = cv2.FaceDetectorYN.create(str(model), "", (1080, 1920), 0.5, 0.3, 50) \
        if model.exists() else None

    best = {"score": -1.0, "at": start}
    t = max(0.0, start)
    while t <= end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        face = None
        if det is not None:
            h, w = frame.shape[:2]
            det.setInputSize((w, h))
            _, faces = det.detect(frame)
            if faces is not None and len(faces):
                f = max(faces, key=lambda b: float(b[14]))
                face = tuple(float(v) for v in f[:4])
        s = score_frame(frame, face, c)
        if s["score"] > best["score"]:
            best = {**s, "at": round(t, 2)}
        t += float(c["step"])
    cap.release()
    return best
