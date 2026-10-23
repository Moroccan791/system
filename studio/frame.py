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

_state: dict[str, str] = {"name": "landscape"}


def set_format(name: str) -> str:
    if name not in FORMATS:
        raise ValueError(f"unknown format {name!r}; pick one of {sorted(FORMATS)}")
    _state["name"] = name
    return name


def name() -> str:
    return _state["name"]


def size() -> tuple[int, int]:
    return FORMATS[_state["name"]]


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
    mode: str          # "cover" | "pad"
    because: str


def fit_for(picture_aspect: float, target_aspect: float) -> Fit:
    """Cover or pad, decided by the PICTURE, not by the file.

    * A picture within reach of the target is cropped to fill — that is what an
      editor does, and the loss is a slice of each side.
    * A much wider picture (2.2:1 and up) holds faces near the edges; cropping it
      to 9:16 keeps a middle third and throws the performance away. Those are
      fitted over a blurred enlargement of themselves, which is the standard
      broadcast answer and reads as a choice. Black bars read as a mistake.
    """
    if target_aspect >= 1.0:            # landscape or square frame
        return Fit("cover" if picture_aspect >= 1.35 else "pad",
                   "landscape target")
    ratio = picture_aspect / target_aspect
    if ratio >= 2.4:
        return Fit("pad", "picture far wider than 9:16 — cropping keeps a third")
    return Fit("cover", "picture close enough to crop")
