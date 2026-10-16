"""Cover / thumbnail frames for a finished clip.

TikTok and Shorts both let the poster choose the cover, and a designed
frame (payoff face + hook text) out-taps a random first frame. The cover
is composed from a frame of the *rendered* clip, so whatever handle or
watermark the clip carries is already on it; this only adds the scrims
and the hook typography (Montserrat ExtraBold, the caption face), with
the last line in the project accent - the same hierarchy as the hook
header inside the video.
"""
from __future__ import annotations

from pathlib import Path

from .. import config

_FONT = config.ROOT / "assets" / "fonts" / "Montserrat-ExtraBold.ttf"


def _scrim(w: int, h: int, *, top: float = 0.52, bottom: float = 0.30):
    """Black gradient overlays: strong at the very top (title zone) and a
    lighter one over the caption zone at the bottom, fading to nothing."""
    from PIL import Image

    overlay = Image.new("L", (1, h), 0)
    px = overlay.load()
    for y in range(h):
        a = 0
        if y < h * top:
            a = max(a, int(205 * (1 - y / (h * top)) ** 1.4))
        if y > h * (1 - bottom):
            a = max(a, int(120 * ((y - h * (1 - bottom)) / (h * bottom)) ** 1.4))
        px[0, y] = a
    return overlay.resize((w, h))


def _fit_font(draw, lines: list[str], max_w: int, start: int):
    from PIL import ImageFont

    size = start
    while size > 24:
        font = ImageFont.truetype(str(_FONT), size)
        if all(draw.textlength(t, font=font) <= max_w for t in lines):
            return font
        size = int(size * 0.92)
    return ImageFont.truetype(str(_FONT), size)


def make_cover(frame: str | Path, out: str | Path, lines: list[str], *,
               accent: str = "#FDFCFD") -> Path:
    """Compose the cover from a still of the finished clip."""
    from PIL import Image, ImageDraw, ImageEnhance

    img = Image.open(frame).convert("RGB")
    w, h = img.size
    img = ImageEnhance.Brightness(img).enhance(0.96)
    img.paste(Image.new("RGB", (w, h), (0, 0, 0)),
              mask=_scrim(w, h).point(lambda a: a))
    draw = ImageDraw.Draw(img)
    lines = [t.strip() for t in lines if t.strip()]
    if not lines:
        raise ValueError("cover needs at least one text line")
    font = _fit_font(draw, lines, int(w * 0.90), int(w * 0.135))
    size = font.size
    stroke = max(2, size // 11)
    y = int(h * 0.062)
    for i, line in enumerate(lines):
        fill = accent if i == len(lines) - 1 and len(lines) > 1 else "#FFFFFF"
        x = (w - draw.textlength(line, font=font)) / 2
        draw.text((x + size * 0.045, y + size * 0.05), line, font=font,
                  fill=(0, 0, 0), stroke_width=stroke, stroke_fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += int(size * 1.16)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
    return out
