"""Point tracking, so a graphic can be pinned to something that moves.

An overedit pins things to the subject: a chip over the shoulder, a word on a
hand, a label on a prop. Doing that by hand is the most tedious part of the
style, and doing it badly is the most obvious — a graphic that slides off the
face by 30 px reads as broken, not as motion.

Method: find a face in the first frame of a shot (Haar cascade, ships with
opencv), then follow it with pyramidal Lucas-Kanade on a sparse feature set
inside the face box. LK is the right tool here — it is sub-pixel, it is cheap,
and film footage is smooth enough that it does not drift much over a second or
two. A long hold would drift; short drop cuts do not.

`track_box` returns the tracked centre for every frame, or None where tracking
was lost, so the caller can decide to fall back to a fixed position rather than
leave a graphic floating in space.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:                                   # cv2 is optional: studio must run without it
    import cv2

    _HAVE_CV2 = True
except Exception:                      # pragma: no cover - import guard
    cv2 = None
    _HAVE_CV2 = False


@dataclass
class Track:
    x: list[float]                 # centre x per frame, in frame pixels
    y: list[float]
    lost: int = 0                  # frames where tracking failed

    def at(self, i: int) -> tuple[float, float] | None:
        if not self.x:
            return None
        i = max(0, min(len(self.x) - 1, i))
        if self.x[i] < 0:
            return None
        return self.x[i], self.y[i]

    @property
    def drift_ok(self) -> bool:
        return self.lost <= max(2, int(0.15 * len(self.x)))


def _face_box(grey: np.ndarray) -> tuple[int, int, int, int] | None:
    """The SUBJECT's face, as (x, y, w, h).

    Largest-face is the wrong rule: in a widescreen shot the biggest face is
    often a background passenger, and a card pinned to them is obviously wrong.
    The subject is big AND near the middle of frame, so score area against
    distance from centre and throw away faces too small to be the subject.
    """
    if not _HAVE_CV2:
        return None
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cas = cv2.CascadeClassifier(path)
    if cas.empty():
        return None
    faces = cas.detectMultiScale(grey, scaleFactor=1.15, minNeighbors=5,
                                 minSize=(48, 48))
    if len(faces) == 0:
        return None

    h_img, w_img = grey.shape[:2]
    min_area = 0.015 * h_img * w_img          # a face smaller than 1.5% is a crowd
    best, best_score = None, -1.0
    for (x, y, w, h) in faces:
        area = w * h
        if area < min_area:
            continue
        cx, cy = x + w / 2, y + h / 2
        d = (((cx - w_img / 2) / (w_img / 2)) ** 2
             + ((cy - h_img / 2) / (h_img / 2)) ** 2) ** 0.5
        score = (area / (h_img * w_img)) * (1.0 - 0.55 * min(1.0, d))
        if score > best_score:
            best, best_score = (int(x), int(y), int(w), int(h)), score
    return best


def track_box(frames: list[np.ndarray], margin: float = 0.6) -> Track | None:
    """Follow the subject's face through a list of BGR/RGB frames.

    `margin` grows the seed box so features on the edges of the face (hair,
    shoulder) also contribute — a face-only patch drifts on a turn.
    """
    if not _HAVE_CV2 or len(frames) < 2:
        return None
    greys = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    box = _face_box(greys[0])
    if box is None:
        return None
    x, y, w, h = box
    mx, my = int(w * margin / 2), int(h * margin / 2)
    x0 = max(0, x - mx)
    y0 = max(0, y - my)
    x1 = min(greys[0].shape[1], x + w + mx)
    y1 = min(greys[0].shape[0], y + h + my)

    mask = np.zeros_like(greys[0])
    mask[y0:y1, x0:x1] = 255
    pts = cv2.goodFeaturesToTrack(greys[0], maxCorners=90, qualityLevel=0.01,
                                  minDistance=8, mask=mask)
    if pts is None or len(pts) < 6:
        return None

    xs, ys = [], []
    lost = 0
    px, py = pts.reshape(-1, 2).mean(axis=0)
    xs.append(float(px))
    ys.append(float(py))

    prev = greys[0]
    cur_pts = pts
    for i in range(1, len(greys)):
        nxt, status, _err = cv2.calcOpticalFlowPyrLK(
            prev, greys[i], cur_pts, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
        if nxt is None or status is None or int(status.sum()) < 4:
            xs.append(-1.0)
            ys.append(-1.0)
            lost += 1
            prev = greys[i]
            continue
        good = nxt[status.ravel() == 1].reshape(-1, 2)
        cx, cy = good.mean(axis=0)
        # a jump of more than a quarter frame in one step means the flow broke
        if abs(cx - px) > greys[0].shape[1] * 0.25 or abs(cy - py) > greys[0].shape[0] * 0.25:
            xs.append(-1.0)
            ys.append(-1.0)
            lost += 1
            prev = greys[i]
            cur_pts = good.reshape(-1, 1, 2).astype(np.float32)
            continue
        xs.append(float(cx))
        ys.append(float(cy))
        px, py = cx, cy
        prev = greys[i]
        cur_pts = good.reshape(-1, 1, 2).astype(np.float32)
    return Track(x=xs, y=ys, lost=lost)


def smooth(track: Track, window: int = 5) -> Track:
    """Median-filter the path.

    Raw LK output jitters by a pixel or two per frame, and a graphic that jitters
    looks like a bug even when the tracking is correct. A short median keeps the
    motion and removes the shake.
    """
    if not track.x or window < 3:
        return track
    xs = np.array(track.x, dtype=np.float32)
    ys = np.array(track.y, dtype=np.float32)
    valid = xs >= 0

    def filt(a: np.ndarray) -> np.ndarray:
        out = a.copy()
        half = window // 2
        for i in range(len(a)):
            lo, hi = max(0, i - half), min(len(a), i + half + 1)
            seg = a[lo:hi]
            seg = seg[seg >= 0] if (seg < 0).any() else seg
            if len(seg):
                out[i] = float(np.median(seg))
        return out

    return Track(x=filt(xs).tolist(), y=filt(ys).tolist(), lost=track.lost)


def has_opencv() -> bool:
    return _HAVE_CV2
