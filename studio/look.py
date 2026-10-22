"""The look layer: what a cut does to the frame, beyond grading it.

Three effects, in the order they earn their place:

  * **punch** — a slow push inside the shot, 2-6%. A held frame with no movement
    reads as a still; a 4% push over 0.8s reads as a camera. This is the single
    cheapest thing that separates an edit from a slideshow, and the reference
    uses it on nearly every held cut.
  * **impact** — a 2-3 frame 6% scale settle on the first frames of a CUT that
    also flashes. It is the picture agreeing with the sound.
  * **grain** — a fine luma noise at 2-3/255. It does two jobs: it makes the
    grade feel like film rather than a filter, and it dithers 8-bit gradients so
    the dark interiors stop showing bands.

What is deliberately NOT here: shake. Handheld jitter is a trend with a shelf
life and it fights type legibility; on a caption-led edit it is a liability, not
a style.

Everything is scaled by act. The build gets a slow push, the drop gets punch on
entry, the exhale gets grain only — an overedit is a rhythm, and the look layer
has to respect the same acts the cuts do.
"""
from __future__ import annotations

import numpy as np

# act -> (push over the cut, impact settle on entry)
PUSH = {"build": 0.020, "drop": 0.045, "out": 0.010}
GRAIN = {"build": 2.0, "drop": 3.0, "out": 4.5}

_GRAIN_FIELD: np.ndarray | None = None


def _field() -> np.ndarray:
    """One 1024² noise plate, reused with a random offset per frame.

    Generating 1920×1080 of gaussian noise per frame costs more than the rest of
    the compositor together; sampling a static plate from a moving offset is
    indistinguishable at 3/255 and about forty times cheaper.
    """
    global _GRAIN_FIELD
    if _GRAIN_FIELD is None:
        rng = np.random.default_rng(7)
        _GRAIN_FIELD = rng.normal(0.0, 1.0, (1024, 1024)).astype(np.float32)
    return _GRAIN_FIELD


def grain(frame: np.ndarray, strength: float, seed: int = 0) -> np.ndarray:
    """Fine luma noise. `strength` is in 0-255 units (2-4 is a film grain)."""
    if strength <= 0.05:
        return frame
    f = _field()
    h, w = frame.shape[:2]
    rng = np.random.default_rng(seed * 2654435761 % (2 ** 32))
    # tile the plate when the frame is bigger than it, rather than indexing off
    # the end: 1080 is taller than the 1024 field and used to raise here.
    ty, tx = -(-h // 1024), -(-w // 1024)
    y, x = int(rng.integers(0, 1024)), int(rng.integers(0, 1024))
    plate = np.tile(f, (ty + 1, tx + 1))[y:y + h, x:x + w]
    noise = plate[..., None] * strength
    out = frame.astype(np.float32) + noise
    return np.clip(out, 0, 255).astype(np.uint8)


def punch(frame: np.ndarray, u: float, amount: float) -> np.ndarray:
    """Push in by `amount` across the cut. `u` is 0..1 through the cut.

    Crops then resizes back to frame size — a real push, not a scale of the
    final image, so the edges never show.
    """
    if amount <= 0.0:
        return frame
    h, w = frame.shape[:2]
    s = 1.0 + amount * min(1.0, max(0.0, u))
    cw, ch = int(round(w / s)), int(round(h / s))
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    crop = frame[y0:y0 + ch, x0:x0 + cw]
    from PIL import Image

    return np.asarray(Image.fromarray(crop).resize((w, h), Image.BILINEAR))


def impact(frame: np.ndarray, k: float) -> np.ndarray:
    """A brief scale settle: `k` 0..1, how far into the settle we are."""
    if k >= 1.0:
        return frame
    return punch(frame, 1.0 - k, 0.06)


def apply(frame: np.ndarray, act: str, u: float, fi: int, seed: int = 0,
          on: bool = True) -> np.ndarray:
    """The whole look, in one call, for one frame."""
    if not on:
        return frame
    push = PUSH.get(act, PUSH["drop"])
    if push and u > 0:
        frame = punch(frame, u, push)
    if fi < 3:
        # entry settle on the first three frames of every cut: 60% -> 30% -> 0.
        frame = impact(frame, (0.6, 0.3, 0.0)[fi])
    return grain(frame, GRAIN.get(act, 3.0), seed + fi)
