"""The handle, bottom centre, every frame.

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


_cache: dict[tuple[int, int], np.ndarray | None] = {}


def stamp(frame: np.ndarray, st: dict | None = None) -> np.ndarray:
    """Composite the handle onto `frame` (H, W, 3 uint8), in place."""
    h, w = frame.shape[:2]
    key = (w, h)
    if key not in _cache:
        _cache[key] = _overlay(w, h, st)
    tile = _cache[key]
    if tile is None:
        return frame
    t = np.asarray(tile, dtype=np.float32) / 255.0
    th, tw = t.shape[:2]
    margin = int(round(h * 0.055))
    x = (w - tw) // 2
    y = max(0, h - margin - th)
    reg = frame[y:y + th, x:x + tw].astype(np.float32) / 255.0
    a = t[..., 3:4]
    reg = reg * (1.0 - a) + t[..., :3] * a
    frame[y:y + th, x:x + tw] = np.clip(reg * 255.0, 0, 255).astype(np.uint8)
    return frame


def clear() -> None:
    """Forget the cached tile — used when the setting changes mid-session."""
    _cache.clear()
