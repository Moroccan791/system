"""Reference 2 type: printed, not captioned.

Reference 1 (the house system, `studio/typecards.py`) sets the lyric as a
centred white card that changes with the vocal. Reference 2 does something the
eye reads as *printed matter laid on the film*:

  * a STACK, right-aligned, that accumulates. Each sung line is added under the
    last and the block grows downward until it is four lines deep, then the
    oldest drops off. You watch a paragraph being written, not a word being
    flashed.
  * a SILVER fill — a vertical gradient from cool white at the cap line to warm
    grey at the baseline — instead of flat paper white. On a dark plate flat
    white reads as a subtitle; a metal fill reads as an object in the frame.
  * a BED: one phrase set enormous, wide-tracked, in crimson, sitting *behind*
    the picture's subject for several seconds. Two copies: a huge ghost at low
    opacity and a small solid one inside it.

Measured off the reference (1280x532, sampled at 10 fps):

    stack right edge      0.95 W, top 0.094 H
    line cap height       0.11 H, line pitch 0.24 H, max 4 lines visible
    bed ghost             0.50 H cap, 0.72 W, alpha 0.40, #7c1119
    bed solid             0.15 H cap, alpha 1.00, #c2131d

Everything is drawn from the alphabetic mask, never from a rectangle, so the
gradient follows the letterforms and the type can sit over a face without a box.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# the reference's own numbers, as fractions of the frame
STACK_RIGHT = 0.95
STACK_TOP = 0.094
LINE_CAP = 0.110
LINE_PITCH = 0.240
MAX_LINES = 4
TRACKING = 0.018          # em — this face is already wide; reference sets it tight
OLDER_ALPHA = (0.34, 0.58, 0.78)   # oldest first, then next, newest is 1.0

# silver: cool at the top of the cap, warm at the baseline, with a bright band
# just under the cap line — that band is what makes it read as metal
SILVER = [(0.00, (246, 246, 247)),
          (0.42, (223, 224, 227)),
          (0.62, (190, 189, 191)),
          (0.86, (205, 196, 186)),
          (1.00, (232, 224, 214))]

BED_GHOST = (124, 17, 25)
BED_SOLID = (194, 19, 29)


def _font(size: int, path: str | Path | None = None) -> ImageFont.FreeTypeFont:
    if path is None:
        from . import fonts

        path = fonts.main()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"no face at {p}")
    return ImageFont.truetype(str(p), size)


def size_for_cap(cap: int, path: str | Path | None = None) -> ImageFont.FreeTypeFont:
    """The point size whose 'H' measures `cap` pixels tall.

    Optical size, not point size: two faces at the same number have different
    cap heights, and this system is defined by the cap height on screen.
    """
    lo, hi = 8, 900
    best = _font(lo, path)
    while lo < hi:
        mid = (lo + hi) // 2
        f = _font(mid, path)
        b = f.getbbox("H")
        h = b[3] - b[1]
        best = f
        if h < cap:
            lo = mid + 1
        else:
            hi = mid
    return best


def _line_mask(text: str, font: ImageFont.FreeTypeFont, tracking: float) -> Image.Image:
    """One line of type as an 8-bit mask, drawn glyph by glyph for tracking."""
    text = text.upper()
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    track = font.size * tracking
    widths = [probe.textlength(ch, font=font) for ch in text]
    w = int(sum(widths) + track * max(0, len(text) - 1)) + 4
    asc, desc = font.getmetrics()
    h = asc + desc + 4
    im = Image.new("L", (max(1, w), h), 0)
    d = ImageDraw.Draw(im)
    x = 2.0
    for ch, cw in zip(text, widths):
        d.text((x, 2), ch, font=font, fill=255)
        x += cw + track
    return im


def _fill(mask: Image.Image, stops=None) -> np.ndarray:
    """RGBA from a mask and a vertical gradient."""
    stops = stops or SILVER
    a = np.asarray(mask, dtype=np.float32) / 255.0
    h, w = a.shape
    ys = np.linspace(0.0, 1.0, h)
    cols = np.zeros((h, 3), dtype=np.float32)
    for c in range(3):
        pts = [s[0] for s in stops]
        vals = [s[1][c] for s in stops]
        cols[:, c] = np.interp(ys, pts, vals)
    rgb = np.repeat(cols[:, None, :], w, axis=1)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    return out


def stack_face(lines: list[str], frame_w: int, frame_h: int,
               font_path: str | Path | None = None,
               right: float = STACK_RIGHT, top: float = STACK_TOP,
               cap: float = LINE_CAP, pitch: float = LINE_PITCH,
               colour: tuple[int, int, int] | None = None,
               lift: float = 0.0) -> "Card":
    """A right-aligned stack of up to four lines, oldest dimmed.

    `lines` is the whole visible stack, oldest first. The caller decides what has
    dropped off; this function only draws it, which keeps the accumulation logic
    where the timings are.

    `lift` 0..1 raises the newest line toward the flash value — the reference's
    cards arrive a stop brighter and settle, which is why they read as events
    rather than as a caption changing.
    """
    from .typecards import Card

    lines = [l for l in lines if l.strip()][-MAX_LINES:]
    if not lines:
        lines = [" "]
    f = size_for_cap(max(8, int(frame_h * cap)), font_path)
    masks = [_line_mask(l, f, TRACKING) for l in lines]
    # A lyric line is longer than the reference's two-word cards, so the block is
    # shrunk until its longest line fits the width it is allowed. Shrinking the
    # whole stack keeps every line at one optical size; shrinking only the long
    # line would make the stack look hand-set by four different people.
    room = frame_w * (right - 0.04)
    widest = max(m.size[0] for m in masks)
    if widest > room:
        k = room / widest
        f = size_for_cap(max(8, int(frame_h * cap * k)), font_path)
        masks = [_line_mask(l, f, TRACKING) for l in lines]
    step = int(frame_h * pitch)
    pad = int(frame_h * 0.02)
    width = max(m.size[0] for m in masks) + pad * 2
    height = step * (len(masks) - 1) + max(m.size[1] for m in masks) + pad * 2

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for i, m in enumerate(masks):
        rgba = _fill(m)
        if colour is not None:
            # a chosen colour keeps the gradient's shape: shading, not a hue swap
            lum = rgba[..., :3].mean(axis=2, keepdims=True) / 255.0
            rgba[..., :3] = np.clip(np.array(colour) * (0.55 + 0.65 * lum), 0, 255)
        alpha = 1.0 if i == len(masks) - 1 else OLDER_ALPHA[max(0, len(masks) - 2 - i)
                                                             % len(OLDER_ALPHA)]
        if lift > 0 and i == len(masks) - 1:
            # toward white, not toward a colour: a flash is light
            rgb = rgba[..., :3].astype(np.float32)
            rgba[..., :3] = np.clip(rgb + (255.0 - rgb) * 0.55 * lift, 0, 255)
        rgba[..., 3] = (rgba[..., 3].astype(np.float32) * alpha).astype(np.uint8)
        layer = Image.fromarray(rgba, "RGBA")
        at = (width - pad - m.size[0], pad + i * step)
        # soft drop shadow, straight down, so the type sits on the plate
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sh.paste(layer, at)
        shadow = sh.filter(ImageFilter.GaussianBlur(max(2, int(f.size * 0.06))))
        sh_px = np.asarray(shadow).astype(np.float32)
        sh_px[..., :3] = 0.0
        sh_px[..., 3] *= 0.55
        canvas.alpha_composite(Image.fromarray(sh_px.astype(np.uint8), "RGBA"),
                               (at[0], at[1] + int(f.size * 0.035)))
        canvas.alpha_composite(layer, at)

    arr = np.asarray(canvas)
    x = int(frame_w * right) - width
    y = int(frame_h * top)
    return Card("\n".join(lines), arr, max(0, x), max(0, y), role="stack")


def bed(frame_w: int, frame_h: int, text: str,
        font_path: str | Path | None = None,
        ghost_cap: float = 0.50, solid_cap: float = 0.15,
        ghost_alpha: float = 0.30) -> "Card":
    """The phrase bed: one huge ghost word behind one small solid word.

    Drawn as a full-frame layer so the compositor can fade it in and out without
    re-rendering the type every frame.
    """
    from .typecards import Card

    canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))

    def place(cap_frac: float, colour, alpha: float, track: float,
              allow_bleed: float = 1.0) -> None:
        f = size_for_cap(max(8, int(frame_h * cap_frac)), font_path)
        m = _line_mask(text, f, track)
        # The reference's ghost runs past the frame edge and is CROPPED — that is
        # what makes it read as something behind the shot rather than as a red
        # subtitle. It may bleed to `allow_bleed` of the width and no further.
        if m.size[0] > frame_w * allow_bleed:
            k = frame_w * allow_bleed / m.size[0]
            m = m.resize((max(1, int(m.size[0] * k)), max(1, int(m.size[1] * k))),
                         Image.LANCZOS)
        rgba = _fill(m, stops=[(0.0, colour), (1.0, colour)])
        rgba[..., 3] = (rgba[..., 3].astype(np.float32) * alpha).astype(np.uint8)
        layer = Image.fromarray(rgba, "RGBA")
        x = (frame_w - layer.size[0]) // 2
        y = int(frame_h * 0.46) - layer.size[1] // 2
        canvas.alpha_composite(layer, (x, y))

    # A three-word refrain set at half frame height is a wall. The ghost is
    # allowed to be enormous; it is not allowed to stop the picture reading, so
    # alpha falls as the phrase gets longer, and its width is capped harder.
    words = len(text.split())
    place(ghost_cap if words <= 2 else ghost_cap * 0.78,
          BED_GHOST, ghost_alpha if words <= 2 else ghost_alpha * 0.66, 0.02,
          allow_bleed=1.16)
    place(solid_cap, BED_SOLID, 1.0, 0.06)
    return Card(text, np.asarray(canvas), 0, 0, role="bed")


def single(text: str, frame_w: int, frame_h: int,
           font_path: str | Path | None = None) -> "Card":
    """The low-right register: one short line, no accumulation.

    Measured off the reference at 3.2 s ("GO"): right edge 0.87 W, band
    0.75-0.91 H, cap 0.15 H. It is the register used when the picture is doing
    the talking and the type is a single beat.
    """
    from .typecards import Card

    f = size_for_cap(max(8, int(frame_h * 0.15)), font_path)
    m = _line_mask(text, f, TRACKING)
    room = frame_w * 0.68
    if m.size[0] > room:
        k = room / m.size[0]
        f = size_for_cap(max(8, int(frame_h * 0.15 * k)), font_path)
        m = _line_mask(text, f, TRACKING)
    rgba = _fill(m)
    arr = np.asarray(Image.fromarray(rgba, "RGBA"))
    x = int(frame_w * 0.87) - arr.shape[1]
    y = int(frame_h * 0.90) - arr.shape[0]
    return Card(text, arr, max(0, x), max(0, y), role="single")
