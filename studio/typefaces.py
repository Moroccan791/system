"""Type layouts — one per style that sets words differently.

The house sets a card with `typecards.render_card`: centred, one line, sized to
a fraction of the frame. Every style below replaces that *placement*, not the
renderer's idea of what a card is, so the compositor still receives a single
`Card` and nothing in the drawing loop has to know a style exists.

Three layouts, each taken from a reference:

  cold_read  small, all caps, bottom-left, killed by the cut it sits on.
             From v5: dialogue fragments that arrive and die with their shot.
  hymn       two voices — a white serif statement with a yellow script
             underneath it, offset right. From v13.
  hype       one word, far too large, bleeding off both edges. From v11; the
             reference puts it BEHIND the subject and we cannot, honestly, so
             it sits over the picture at low alpha and reads as texture.
"""

from __future__ import annotations

from pathlib import Path

from .typecards import Card

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SERIF = ASSETS / "DejaVuSerif-Bold.ttf"
SCRIPT = ASSETS / "Flaviotte.ttf"
CONDENSED = ASSETS / "CabinetGrotesk-Black.otf"


def _font(path: Path, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(path), max(6, int(size)))


def _card_from_image(im, x: int, y: int, text: str, role: str = "line") -> Card:
    import numpy as np

    return Card(text=text, rgba=np.asarray(im), x=int(x), y=int(y), role=role)


# ---------------------------------------------------------------------------
# cold_read — the subtitle that dies on the cut
# ---------------------------------------------------------------------------
def cold_read(text: str, w: int = 1920, h: int = 1080) -> Card:
    """Small caps, bottom-left, no shadow, no tracking.

    v5's fragments sit in the lower third and never centre. The size is fixed
    (about 3.4% of frame height) because a fragment that changes size from line
    to line stops reading as one person speaking.
    """
    from PIL import Image, ImageDraw

    body = text.strip().upper()
    px = int(h * 0.034)
    font = _font(ASSETS / "Montserrat-SemiBold.ttf", px)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = int(probe.textlength(body, font=font))
    pad = int(px * 0.55)
    im = Image.new("RGBA", (max(1, tw + pad * 2), int(px * 2.1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # a tight shadow only: the reference's type sits on dark plates, and a halo
    # on a subtitle is the tell of a caption tool rather than an edit
    d.text((pad + 2, pad * 0.5 + 2), body, font=font, fill=(0, 0, 0, 150))
    d.text((pad, pad * 0.5), body, font=font, fill=(255, 255, 255, 235))

    x = int(w * 0.055)
    y = int(h * 0.795)
    return _card_from_image(im, x, y, text, "fragment")


# ---------------------------------------------------------------------------
# hymn — two voices, one line
# ---------------------------------------------------------------------------
def hymn(text: str, w: int = 1920, h: int = 1080) -> Card:
    """White serif states the line; yellow script signs it underneath.

    v13 pairs the two on every occurrence, the script sitting lower and to the
    right, as if written on afterwards. They are one card here so the rest of
    the renderer sees a single object.
    """
    from PIL import Image, ImageDraw

    line = " ".join(text.strip().split()[:3]).upper()
    if not line:
        return _card_from_image(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), 0, 0, text)

    # v13's two voices carry DIFFERENT words — the serif states, the script
    # answers. We only have one word source (the lyric line), so the line is
    # split across the two faces rather than set twice.
    words = text.strip().split()
    head = " ".join(words[:max(1, len(words) // 2)]) if len(words) > 1 else ""
    tail = " ".join(words[len(words) // 2:]) if len(words) > 1 else text.strip()

    serif_px = int(h * 0.062)
    script_px = int(h * 0.072)
    f_serif = _font(SERIF, serif_px)
    f_script = _font(SCRIPT, script_px)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w1 = int(probe.textlength(line, font=f_serif))
    w2 = int(probe.textlength(tail, font=f_script))
    width = max(w1, w2) + int(h * 0.06)
    height = int(serif_px * 1.15 + script_px * 1.45)

    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text(((width - w1) // 2, 0), line, font=f_serif, fill=(255, 255, 255, 245))
    # the script runs under the serif, pushed right, in the reference's yellow
    d.text(((width - w2) // 2 + int(h * 0.030), int(serif_px * 1.12)),
           tail, font=f_script, fill=(255, 209, 37, 240))

    x = (w - width) // 2
    y = int(h * 0.46)
    return _card_from_image(im, x, y, text, "duet")


# ---------------------------------------------------------------------------
# hype — one word, bigger than the frame
# ---------------------------------------------------------------------------
def hype(text: str, w: int = 1920, h: int = 1080) -> Card:
    """A word set to about 1.15x the frame width, cropped by the edges.

    The reference sets its type BEHIND the subject at this scale, which needs a
    matte we do not have. Drawing it over the picture at low alpha gets the
    scale and the rhythm honestly; it does not claim to be behind anything.
    """
    from PIL import Image, ImageDraw

    word = max(text.split(), key=len).upper() if text.split() else ""
    if not word:
        return _card_from_image(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), 0, 0, text)

    px = int(h * 0.30)
    font = _font(CONDENSED, px)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = int(probe.textlength(word, font=font))
    im = Image.new("RGBA", (max(1, tw + 8), int(px * 1.25)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((6, 5), word, font=font, fill=(0, 0, 0, 105))
    d.text((4, 0), word, font=font, fill=(255, 255, 255, 190))

    # centre it, and let it overrun the frame edges the way the reference does
    x = (w - im.size[0]) // 2
    y = int(h * 0.33)
    return _card_from_image(im, x, y, text, "huge")


LAYOUTS = {"cold_read": cold_read, "hymn": hymn, "hype": hype}


def for_style(style: str | None):
    return LAYOUTS.get(style or "")
