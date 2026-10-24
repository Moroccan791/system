"""Frame geometry and where type is allowed to sit.

Two separate problems, both about the same word — "frame":

* **Which shape the edit is.** A vertical is 1080x1920, and nothing about the
  type rules changes except the numbers.
* **Where the picture is inside that shape.** Many scenepacks are a 16:9 file
  with the film's wider image letterboxed into it, so the black bands are part
  of the footage. Reframing such a file by its FILE aspect crops the bars and
  calls it a vertical; the picture then has to be found first, or you are
  cropping black.

And one thing that is not about frames at all: **the platforms draw on top of
the video.** On a vertical, the bottom fifth carries the caption, the handle and
the buttons, and the top tenth carries the header. Type that lands there is not
"almost right" — it is unreadable, because something else is on top of it. So
captions get a safe zone measured in fractions of the frame, and the type is
placed inside it rather than centred on the whole canvas.
"""
from __future__ import annotations

from dataclasses import dataclass

# name -> (width, height)
FORMATS: dict[str, tuple[int, int]] = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
}

# Where the platform puts its own furniture, as fractions of the frame.
# Vertical is the only one that really matters — Reels/TikTok/Shorts all put the
# caption block, the handle and the action rail across the bottom ~22%, and the
# account/back header across the top ~10%.
SAFE: dict[str, dict[str, float]] = {
    "landscape": {"top": 0.05, "bottom": 0.08, "side": 0.05},
    "vertical": {"top": 0.10, "bottom": 0.22, "side": 0.06},
    "square": {"top": 0.07, "bottom": 0.16, "side": 0.05},
}

_state: dict[str, str] = {"name": "landscape", "scale": 1.0}


def set_format(name: str) -> str:
    if name not in FORMATS:
        raise ValueError(f"unknown format {name!r}; pick one of {sorted(FORMATS)}")
    _state["name"] = name
    return name


def name() -> str:
    return _state["name"]


def set_scale(k: float) -> float:
    """Render at a fraction of the delivery size.

    Not a style, a memory budget. `compose.decode_segment` holds every frame of
    a cut before it composites, so a 6.5 s hold at 1080p is ~1.2 GB of RGB and
    the box this ran on has 3.9 GB — the render was OOM-killed at exit 137. Half
    size is a quarter of the pixels, which is the difference between a review
    copy and no copy at all.
    """
    _state["scale"] = max(0.1, min(1.0, float(k)))
    return _state["scale"]


def scale() -> float:
    return _state.get("scale", 1.0)


def size() -> tuple[int, int]:
    w, h = FORMATS[_state["name"]]
    k = _state.get("scale", 1.0)
    if k != 1.0:
        # even numbers only: x264 wants them, and an odd height is rejected
        return (int(round(w * k / 2)) * 2, int(round(h * k / 2)) * 2)
    return (w, h)


def is_vertical() -> bool:
    w, h = size()
    return h > w


def safe() -> dict[str, float]:
    return dict(SAFE[_state["name"]])


def caption_zone(height: int | None = None) -> tuple[int, int]:
    """The band captions may occupy, in pixels: (top, bottom).

    Centred inside the safe area rather than the frame. On a vertical that moves
    the words up out of the caption block; on a landscape it is nearly the same
    place as before.
    """
    h = height or size()[1]
    s = safe()
    return int(round(h * s["top"])), int(round(h * (1.0 - s["bottom"])))


def caption_centre(height: int | None = None) -> int:
    top, bottom = caption_zone(height)
    return (top + bottom) // 2


def side_margin(width: int | None = None) -> int:
    w = width or size()[0]
    return int(round(w * safe()["side"]))


def safe_width(width: int | None = None) -> int:
    """Widest a line of type may be before it leaves the safe area."""
    w = width or size()[0]
    return w - 2 * side_margin(w)


@dataclass
class Fit:
    """What to do with a source picture when the frame is a different shape."""
    mode: str          # "cover" | "slice" | "pad"
    because: str


# For a vertical frame, a wide picture is cropped to this aspect and then sat
# inside the frame. 4:5 is the number that matters: a 2.35:1 picture cropped to
# 4:5 keeps a third of its width and FILLS 70% of the height, which is a real
# crop. Fitting the whole 2.35 width instead leaves a 445px strip of picture in a
# 1920px frame — the subject is a band in the middle and everything above and
# below it is filler. That is the mistake this constant exists to prevent.
VERTICAL_CROP = 0.80          # 4:5


def fit_for(picture_aspect: float, target_aspect: float) -> Fit:
    """Cover, crop-then-pad, or pad — decided by the PICTURE, not by the file."""
    if target_aspect >= 1.0:            # landscape or square frame
        return Fit("cover" if picture_aspect >= 1.35 else "pad",
                   "landscape target")
    # vertical frame
    if picture_aspect <= target_aspect + 0.05:
        return Fit("cover", "already tall enough to fill")
    if picture_aspect >= 1.9:
        # far wider than 9:16: a full cover keeps ~23% of the width and cuts the
        # second person out of every two-shot. Crop to 4:5 instead, which keeps a
        # third and still puts a face at a usable size.
        return Fit("slice", "wide picture — crop to 4:5, not to a sliver")
    return Fit("cover", "close enough to crop to 9:16")
