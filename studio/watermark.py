"""The handle, bottom centre OF THE PICTURE, every frame.

An edit account is recognised by its credits line, not by a logo nobody can read
at a glance. This is the one element on the frame that is NOT part of the design
system: it takes a plain text face (DejaVu Sans by default), not one of the edit
faces, because a watermark that competes with the type is a second voice in the
edit. It is small, half-transparent, and identical on every frame — it never
moves, never fades, never animates.

    assets/fonts/family.json
        "watermark": "@fayzann.edits"
        "watermark_font": "DejaVuSans.ttf"
        "watermark_frac": 0.021        # cap size as a fraction of frame height
        "watermark_alpha": 0.62

An empty or missing value turns it off, so a video for someone else is a data
change and not a code change.

The handle goes on the IMAGE, not on the frame. A scenepack is often a 16:9 file
with the film's 2.05:1 picture letterboxed inside it — the black bands are
baked into the footage, not added by the renderer. Measuring from the frame's
bottom edge put the handle in that band, floating in black under the picture,
which looks like a caption on the canvas rather than a credit on the edit. The
box is measured from the pixel data instead, and the handle sits a fixed
fraction inside its bottom edge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FONT_DIR = Path("assets/fonts")
# Plain faces only. A watermark is legibility, not typography.
PLAIN = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSerif.ttf")

# The account handle is ON unless it is explicitly turned off. It used to be
# "off unless the key is present", and one font change rewrote family.json
# without the key — which silently shipped a watermark-free video and said
# nothing. A default that can only be disabled on purpose is the only safe
# shape for a standing requirement.
DEFAULT_HANDLE = "@fayzann.edits"


def _font_path(name: str | None) -> str | None:
    for cand in ([name] if name else []) + list(PLAIN):
        if not cand:
            continue
        for base in (FONT_DIR, Path("/usr/share/fonts/truetype/dejavu")):
            p = base / cand
            if p.exists():
                return str(p)
    return None


def settings() -> dict:
    from . import fonts

    cfg = fonts.config()
    raw = cfg["watermark"] if "watermark" in cfg else DEFAULT_HANDLE
    text = str(raw).strip()
    return {"text": text,
            "font": _font_path(cfg.get("watermark_font")),
            "frac": float(cfg.get("watermark_frac") or 0.021),
            "alpha": float(cfg.get("watermark_alpha") or 0.62)}


def _overlay(width: int, height: int, st: dict | None = None):
    """The handle rendered once, as an RGBA tile. None when there is no handle."""
    st = st or settings()
    if not st["text"] or not st["font"]:
        return None
    from PIL import Image, ImageDraw, ImageFont

    size = max(10, int(round(height * st["frac"])))
    font = ImageFont.truetype(st["font"], size)
    x0, y0, x1, y1 = font.getbbox(st["text"])
    pad = max(2, size // 4)
    tile = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    # A hairline shadow, not a glow: the handle sits over whatever the cut gives
    # it, and a plain white line over a white wall disappears.
    d.text((pad - x0 + 1, pad - y0 + 1), st["text"], font=font,
           fill=(0, 0, 0, int(255 * st["alpha"] * 0.55)))
    d.text((pad - x0, pad - y0), st["text"], font=font,
           fill=(255, 255, 255, int(255 * st["alpha"])))
    return tile


def _bands(profile: np.ndarray, flat_tol: float, dark: float,
           cap: float) -> tuple[int, int]:
    """Leading and trailing run of near-black, near-flat rows (or columns)."""
    lo, hi = 0, len(profile) - 1
    limit = int(len(profile) * cap)
    while lo < limit and profile[lo] < dark:
        lo += 1
    while hi > len(profile) - 1 - limit and profile[hi] < dark:
        hi -= 1
    return lo, hi


def content_rect(frames: np.ndarray | list[np.ndarray]) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the picture inside the frame — the part that MOVES.

    `frames` is one grey frame or a stack of them. A stack is the honest way:
    black bars are black in every frame, and so is any flat padding, while a
    genuinely dark shot is only dark in the frames that are dark. The median
    across frames therefore leaves only the padding.
    """
    a = np.asarray(frames, dtype=np.float32)
    if a.ndim == 2:
        a = a[None, ...]
    rows = np.median(a.mean(axis=2), axis=0)
    cols = np.median(a.mean(axis=1), axis=0)
    y0, y1 = _bands(rows, 6.0, 14.0, 0.32)
    x0, x1 = _bands(cols, 6.0, 14.0, 0.32)
    if y1 - y0 < 8:
        y0, y1 = 0, a.shape[1] - 1
    if x1 - x0 < 8:
        x0, x1 = 0, a.shape[2] - 1
    return int(x0), int(y0), int(x1), int(y1)


def rect_from_video(path: str | Path, out_w: int, out_h: int,
                    samples: int = 9) -> tuple[int, int, int, int] | None:
    """Measure the picture box of a file, in `out_w` x `out_h` pixels.

    Sampled at low resolution and scaled back up: the band edge is a straight
    line, so a 192-wide sample locates it to within a pixel of the full-size
    answer, and nine frames of a 6-minute pack cost a second.
    """
    import subprocess

    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run([ff, "-nostdin", "-i", str(path)],
                           capture_output=True, text=True)
    dur = 0.0
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
            dur = int(hh) * 3600 + int(mm) * 60 + float(ss)
            break
    if dur <= 0:
        return None
    w, h = 192, 108
    grabs: list[np.ndarray] = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        raw = subprocess.run([ff, "-nostdin", "-v", "error", "-ss", f"{t:.2f}",
                              "-i", str(path), "-frames:v", "1",
                              "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                             capture_output=True).stdout
        if len(raw) >= w * h:
            grabs.append(np.frombuffer(raw[:w * h], dtype=np.uint8).reshape(h, w))
    if not grabs:
        return None
    x0, y0, x1, y1 = content_rect(grabs)
    sx, sy = out_w / w, out_h / h
    return (int(round(x0 * sx)), int(round(y0 * sy)),
            int(round(x1 * sx)), int(round(y1 * sy)))


_cache: dict[tuple[int, int], np.ndarray | None] = {}
_rect_cache: dict[tuple[int, int], tuple[int, int, int, int] | None] = {}


def stamp(frame: np.ndarray, st: dict | None = None,
          rect: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Composite the handle onto `frame` (H, W, 3 uint8), in place.

    `rect` is the picture box in FRAME pixels — pass the same one every frame so
    the handle cannot drift between shots. Without it the box is measured from
    the frame itself and remembered per size.
    """
    h, w = frame.shape[:2]
    key = (w, h)
    if key not in _cache:
        _cache[key] = _overlay(w, h, st)
    tile = _cache[key]
    if tile is None:
        return frame
    t = np.asarray(tile, dtype=np.float32) / 255.0
    th, tw = t.shape[:2]
    if rect is None:
        if key not in _rect_cache:
            _rect_cache[key] = _rect_of_frame(frame)
        rect = _rect_cache[key]
    x0, y0, x1, y1 = rect
    # margin is a fraction of the PICTURE, not of the frame: on a letterboxed
    # file those are very different numbers and the frame one lands in the bar.
    margin = int(round((y1 - y0) * 0.035))
    x = x0 + ((x1 - x0) - tw) // 2
    y = y1 - margin - th
    y = max(y0, min(y, y1 - th))
    x = max(x0, min(x, x1 - tw))
    reg = frame[y:y + th, x:x + tw].astype(np.float32) / 255.0
    a = t[..., 3:4]
    reg = reg * (1.0 - a) + t[..., :3] * a
    frame[y:y + th, x:x + tw] = np.clip(reg * 255.0, 0, 255).astype(np.uint8)
    return frame


def _rect_of_frame(frame: np.ndarray) -> tuple[int, int, int, int]:
    h, w = frame.shape[:2]
    grey = frame.mean(axis=2) if frame.ndim == 3 else frame
    return content_rect(grey)


def clear() -> None:
    """Forget the cached tile — used when the setting changes mid-session."""
    _cache.clear()
    _rect_cache.clear()
