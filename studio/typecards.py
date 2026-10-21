"""Type as an instrument, not a caption.

In an overedit the words are not subtitles — they are the only thing moving
during the build. Three consequences shape this module:

  * the card is sized to the FRAME, not to a font size someone guessed. A card
    that is 15-20% of frame height reads at arm's length on a phone; anything
    smaller is decoration.
  * one to three words. Four words and the eye has to read instead of feel.
  * the type has tracking (letter spacing). Tight type looks cheap at this size;
    open tracking is what makes it look designed.

`render_card` returns a cropped RGBA array plus where it goes, so the compositor
composites a small image instead of carrying a full-frame layer per card.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "assets/fonts/CabinetGrotesk-Black.otf"
FONT_FALLBACK = "assets/fonts/Montserrat-ExtraBold.ttf"


@dataclass
class Card:
    text: str
    rgba: np.ndarray      # (h, w, 4) uint8, cropped
    x: int
    y: int
    role: str = "line"

    def scaled(self, k: float) -> "Card":
        """A copy scaled about its own centre — the 1-frame pop on entry."""
        im = Image.fromarray(self.rgba, "RGBA")
        w, h = im.size
        im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
        nx = self.x + (w - im.size[0]) // 2
        ny = self.y + (h - im.size[1]) // 2
        return Card(self.text, np.asarray(im), nx, ny, self.role)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in (FONT, FONT_FALLBACK):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise FileNotFoundError("no display font found in assets/fonts")


def _measure(draw, text: str, font, tracking: int) -> tuple[int, int]:
    """Width including tracking, and the cap height we will actually draw."""
    if not text:
        return 0, 0
    words = text.split(" ")
    w = int(sum(draw.textlength(wd, font=font) for wd in words)
            + tracking * 1.6 * max(0, len(words) - 1))
    asc, desc = font.getmetrics()
    return w, asc + desc


def render_card(text: str, frame_w: int = 1920, frame_h: int = 1080,
                width_frac: float = 0.62, accent: str | None = None,
                colour: tuple[int, int, int] = (255, 255, 255),
                accent_colour: tuple[int, int, int] = (46, 204, 113),
                tracking_frac: float = 0.06, shadow: bool = True) -> Card:
    """Draw one card, sized so its width is a fraction of the frame.

    `accent` is a word (or a character range marker) to paint in the accent
    colour. In a white-on-white system the accent is the only colour on screen,
    so it has to be earned by the line, not sprinkled.
    """
    words = text.split()
    if len(words) > 3:
        # keep the three heaviest words; a card is a beat, not a sentence
        words = sorted(words, key=len, reverse=True)[:3]
        words = [w for w in text.split() if w in words][:3]
    body = " ".join(words).upper()
    if not body:
        body = " "

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    target_w = int(frame_w * width_frac)

    # binary-search the font size that fills the target width
    lo, hi, size = 24, int(frame_h * 0.42), int(frame_h * 0.12)
    best = size
    for _ in range(18):
        font = _load_font(size)
        tracking = max(1, int(size * tracking_frac))
        w, _h = _measure(probe, body, font, tracking)
        if w < target_w:
            lo = size
        else:
            hi = size
        if abs(w - target_w) < target_w * 0.02:
            best = size
            break
        best = size
        size = (lo + hi) // 2
        if hi - lo <= 2:
            break
    # Cap by HEIGHT as well as width. Three short words at 62% frame width means
    # a glyph the height of a third of the frame — that is a poster, not a beat.
    max_h = int(frame_h * 0.26)
    while best > 12:
        f = _load_font(best)
        if f.getmetrics()[0] + f.getmetrics()[1] <= max_h:
            break
        best = int(best * 0.94)
    font = _load_font(best)
    tracking = max(1, int(best * tracking_frac))
    w, h = _measure(probe, body, font, tracking)

    pad = int(best * 0.35)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    accent = (accent or "").upper()

    def draw_run(dy: int, fill_white, fill_accent, alpha: int):
        # Word by word, not character by character: drawing glyphs individually
        # throws away the font's kerning and "MADE" renders as "MAD E".
        # Tracking belongs BETWEEN words, not inside them.
        x = pad
        for wi, word in enumerate(body.split(" ")):
            if wi:
                x += tracking * 1.6
            wx = x
            for ch in word:
                f = fill_accent if accent and ch in accent else fill_white
                draw.text((wx, pad + dy), ch, font=font,
                          fill=(f[0], f[1], f[2], alpha))
                wx += draw.textlength(ch, font=font)
            x = wx

    if shadow:
        draw_run(int(best * 0.035), (0, 0, 0), (0, 0, 0), 110)
    draw_run(0, colour, accent_colour, 255)

    arr = np.asarray(canvas)
    x = (frame_w - arr.shape[1]) // 2
    y = (frame_h - arr.shape[0]) // 2
    return Card(body, arr, x, y)


def render_stack(lines: list[str], frame_w: int = 1920, frame_h: int = 1080,
                 gap_frac: float = 0.012) -> Card:
    """Two-line lockup, for the one card per edit that deserves weight."""
    cards = [render_card(t, frame_w, frame_h, width_frac=0.62) for t in lines if t.strip()]
    if not cards:
        return render_card(" ", frame_w, frame_h)
    gap = int(frame_h * gap_frac)
    total_h = sum(c.rgba.shape[0] for c in cards) + gap * (len(cards) - 1)
    widths = max(c.rgba.shape[1] for c in cards)
    canvas = Image.new("RGBA", (widths, total_h), (0, 0, 0, 0))
    y = 0
    for c in cards:
        im = Image.fromarray(c.rgba, "RGBA")
        canvas.alpha_composite(im, ((widths - im.size[0]) // 2, y))
        y += im.size[1] + gap
    arr = np.asarray(canvas)
    return Card("\n".join(lines), arr, (frame_w - widths) // 2,
                (frame_h - total_h) // 2, role="stack")


def scrim(frame: np.ndarray, card: Card, amount: float = 0.22,
          blur: int = 26) -> np.ndarray:
    """Darken behind the glyphs themselves, not a rectangle around them.

    White text over a bright wall is unreadable, but a grey box behind it looks
    like a lower third from 2016. Blurring the card's own alpha gives a halo that
    hugs the letterforms, which reads as a shadow, not a panel.
    """
    if amount <= 0:
        return frame
    alpha = card.rgba[..., 3]
    if alpha.max() == 0:
        return frame
    mask = Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(blur))
    m = np.asarray(mask).astype(np.float32) / 255.0
    m = np.clip(m * 2.2, 0.0, 1.0)

    h, w = m.shape
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, card.x), max(0, card.y)
    x1, y1 = min(fw, card.x + w), min(fh, card.y + h)
    if x1 <= x0 or y1 <= y0:
        return frame
    mm = m[y0 - card.y:y1 - card.y, x0 - card.x:x1 - card.x]
    region = frame[y0:y1, x0:x1].astype(np.float32)
    # a touch of lift as well as darkening keeps the halo from looking like dirt
    frame[y0:y1, x0:x1] = np.clip(
        region * (1.0 - amount * mm[..., None]), 0, 255).astype(np.uint8)
    return frame


def composite(frame: np.ndarray, card: Card, alpha: float = 1.0) -> np.ndarray:
    """Alpha-composite a card onto an RGB frame in place-ish."""
    if alpha <= 0:
        return frame
    h, w = card.rgba.shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, card.x), max(0, card.y)
    x1, y1 = min(fw, card.x + w), min(fh, card.y + h)
    if x1 <= x0 or y1 <= y0:
        return frame
    sub = card.rgba[y0 - card.y:y1 - card.y, x0 - card.x:x1 - card.x]
    a = (sub[..., 3:4].astype(np.float32) / 255.0) * alpha
    dst = frame[y0:y1, x0:x1].astype(np.float32)
    src = sub[..., :3].astype(np.float32)
    frame[y0:y1, x0:x1] = (src * a + dst * (1 - a)).astype(np.uint8)
    return frame


if __name__ == "__main__":
    c = render_card("I NEED IS A BEAUTY", accent="NEED BEAUTY")
    print("card", c.rgba.shape, "at", c.x, c.y)
    Image.fromarray(c.rgba, "RGBA").save("work/studio/card_test.png")
