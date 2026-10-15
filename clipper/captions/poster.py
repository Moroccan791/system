"""Poster captions + claim cards + stickers (the next-level format).

Decoded from the reference shorts (recipes/next_level_format.md): the
captions are graphic design, not subtitles. Words stack centre-frame as
a poster - connectives small (serif when the words are pure filler), the
keyword huge in the project accent - appearing exactly when spoken. On
top of that grammar sit full-screen kinetic CLAIM CARDS (the claim
re-shown as a poster while the speaker pauses) and persistent STICKERS
(proof numbers, accumulating lists).

Same hard rules as every mode: words are exactly what was said, in true
sync; nothing is placed over the face zone (cards centre low, QC checks
every poster's bounding stack against detected faces).
"""
from __future__ import annotations

from pathlib import Path

from ..asr.base import Word
from .ass import ass_color, fmt_ass
from .block import (build_hook_events, censor_text, declutter,
                    pick_emphasis, segment_sentences, _text_width)

FILLER = {"the", "a", "an", "to", "of", "and", "or", "is", "it", "in", "on",
          "that", "this", "for", "with", "you", "i", "we", "he", "she",
          "they", "be", "are", "was", "so", "but", "if", "when", "just"}


def _clean(word: str) -> str:
    return censor_text(str(word))


def _poster_events(sentence: list[Word], style: dict, *, width: int,
                   height: int, poster: dict,
                   hard_end: float | None) -> tuple[list[str], tuple[float, float, float, float]]:
    """One spoken chunk as a centre-frame stack. Returns events + bbox."""
    cap = style.get("captions", {}) or {}
    scale = height / 1920.0
    base = float(poster.get("base_size_ass") or 88) * scale
    key_size = base * float(poster.get("keyword_scale") or 1.95)
    small_size = base * float(poster.get("small_scale") or 0.70)
    serif = str(poster.get("serif_font") or "DejaVu Serif")
    sans = str(cap.get("font_name") or "Montserrat")
    accent = poster.get("keyword_color") or (style.get("captions", {})
                                             .get("block", {})
                                             .get("emphasis_color"))
    cy = height * float(poster.get("center_y") or 0.66)

    emph = pick_emphasis(sentence)
    before = sentence[:emph]
    keyword = sentence[emph]
    after = sentence[emph + 1:]

    def is_filler_row(ws: list[Word]) -> bool:
        return all(str(w.text).strip(".,!?\"'").lower() in FILLER for w in ws)

    rows: list[dict] = []
    if before:
        rows.append({"words": before, "size": small_size,
                     "serif": is_filler_row(before), "key": False})
    rows.append({"words": [keyword], "size": key_size, "serif": False,
                 "key": True})
    if after:
        rows.append({"words": after, "size": small_size,
                     "serif": is_filler_row(after), "key": False})

    gap = base * 0.22
    total_h = sum(r["size"] * 1.18 for r in rows) + gap * (len(rows) - 1)
    y = cy - total_h / 2.0
    end = float(sentence[-1].end) + float(poster.get("clear_after") or 0.30)
    if hard_end is not None:
        end = min(end, max(float(sentence[-1].end) + 0.08, hard_end))

    events: list[str] = []
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        size = r["size"]
        row_words = r["words"]
        row_w = sum(_text_width(_clean(w.text), size) for w in row_words) \
            + (len(row_words) - 1) * size * 0.30
        xs += [width / 2 - row_w / 2, width / 2 + row_w / 2]
        ys += [y, y + size * 1.18]
        font = serif if r["serif"] else sans
        for k, w in enumerate(row_words):
            shown = " ".join(_clean(x.text) for x in row_words[: k + 1])
            shown_disp = shown.upper() if r["key"] else shown
            tags = (rf"\an5\pos({width / 2:.0f},{y + size * 0.59:.0f})"
                    rf"\fn{font}\fs{size:.0f}\fad(70,0)")
            if r["key"]:
                tags += r"\fscx124\fscy124\t(0,130,\fscx100\fscy100)"
                if accent:
                    tags += rf"\1c{ass_color(str(accent))}"
            step_end = (float(row_words[k + 1].start)
                        if k + 1 < len(row_words) else end)
            events.append(f"Dialogue: 1,{fmt_ass(float(w.start))},{fmt_ass(step_end)},"
                          f"Poster,,0,0,0,,{{{tags}}}{shown_disp}")
        y += size * 1.18 + gap
    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)
    return events, bbox


def _card_events(card: dict, *, width: int, height: int,
                 poster: dict) -> list[str]:
    """A full-screen claim card: brand panel + lines staggering in."""
    at = float(card.get("at") or 0.0)
    dur = float(card.get("dur") or 1.6)
    bg = ass_color(str(card.get("bg") or poster.get("card_bg") or "#0D1B2E"))
    accent = card.get("accent") or poster.get("keyword_color")
    lines = [str(x) for x in card.get("lines") or [] if str(x).strip()]
    if not lines:
        return []
    events = [f"Dialogue: 4,{fmt_ass(at)},{fmt_ass(at + dur)},Card,,0,0,0,,"
              rf"{{\an7\pos(0,0)\1c{bg}\p1}}m 0 0 l {width} 0 l {width} {height} l 0 {height}{{\p0}}"]
    fs = float(poster.get("card_size_ass") or 148) * (height / 1920.0)
    total_h = fs * 1.16 * len(lines)
    y = height * 0.46 - total_h / 2.0
    for i, line in enumerate(lines):
        start = at + 0.10 + i * 0.26
        tags = (rf"\an5\pos({width / 2:.0f},{y + fs * 0.58:.0f})\fs{fs:.0f}"
                r"\fad(70,120)\fscx118\fscy118\t(0,140,\fscx100\fscy100)")
        if accent and i == len(lines) - 1:
            tags += rf"\1c{ass_color(str(accent))}"
        events.append(f"Dialogue: 5,{fmt_ass(start)},{fmt_ass(at + dur)},Card,,0,0,0,,"
                      f"{{{tags}}}{censor_text(line.upper())}")
        y += fs * 1.16
    sub = str(card.get("sub") or "").strip()
    if sub:
        events.append(f"Dialogue: 5,{fmt_ass(at + 0.10 + len(lines) * 0.26)},"
                      f"{fmt_ass(at + dur)},Card,,0,0,0,,"
                      rf"{{\an5\pos({width / 2:.0f},{y + fs * 0.2:.0f})"
                      rf"\fs{fs * 0.42:.0f}\fad(90,120)}}{censor_text(sub)}")
    return events


def _sticker_events(sticker: dict, *, width: int, height: int,
                    poster: dict) -> list[str]:
    """A persistent badge (BorderStyle=3 gives the chip behind the text)."""
    at = float(sticker.get("at") or 0.0)
    dur = float(sticker.get("dur") or 4.0)
    pos = str(sticker.get("pos") or "tl").lower()
    scale = height / 1920.0
    margin = 54 * scale
    anchor = {"tl": (7, margin, margin), "tr": (9, width - margin, margin),
              "bl": (1, margin, height - 460 * scale),
              "br": (3, width - margin, height - 460 * scale)}.get(
                  pos, (7, margin, margin))
    align, x, y = anchor
    text = censor_text(str(sticker.get("text") or ""))
    sub = str(sticker.get("sub") or "").strip()
    body = text.upper() + (rf"\N{{\fs{int(44 * scale)}}}{censor_text(sub)}"
                           if sub else "")
    return [f"Dialogue: 2,{fmt_ass(at)},{fmt_ass(at + dur)},Sticker,,0,0,0,,"
            rf"{{\an{align}\pos({x:.0f},{y:.0f})\fad(140,180)}}{body}"]


def _list_events(lst: dict, *, width: int, height: int,
                 poster: dict) -> list[str]:
    """An accumulating numbered list: each item lands and stays."""
    at = float(lst.get("at") or 0.0)
    dur = float(lst.get("dur") or 6.0)
    step = float(lst.get("step") or 0.6)
    items = [str(x) for x in lst.get("items") or [] if str(x).strip()]
    scale = height / 1920.0
    x, y = 54 * scale, height * float(lst.get("y") or 0.30)
    events = []
    for k in range(len(items)):
        start = at + k * step
        stop = at + (k + 1) * step if k + 1 < len(items) else at + dur
        shown = r"\N".join(f"{i + 1}  {censor_text(t.upper())}"
                           for i, t in enumerate(items[: k + 1]))
        events.append(f"Dialogue: 2,{fmt_ass(start)},{fmt_ass(stop)},Sticker,,0,0,0,,"
                      rf"{{\an7\pos({x:.0f},{y:.0f})\fad(120,0)}}{shown}")
    return events


def build_poster_ass(words: list[Word], style: dict, *, width: int = 1080,
                     height: int = 1920, end: float | None = None,
                     hook_lines: list[str] | None = None,
                     outro_text: str | None = None,
                     handle: str | None = None,
                     cards: list[dict] | None = None,
                     stickers: list[dict] | None = None,
                     lists: list[dict] | None = None) -> tuple[str, list[dict]]:
    """A complete .ass in poster mode, plus the block list it encodes."""
    cap = style.get("captions", {}) or {}
    poster = cap.get("poster", {}) or {}
    block_cfg = cap.get("block", {}) or {}
    if not poster.get("keyword_color") and block_cfg.get("emphasis_color"):
        poster = {**poster, "keyword_color": block_cfg["emphasis_color"]}
    scale = height / 1920.0
    font_name = cap.get("font_name") or "Montserrat"
    primary = ass_color(cap.get("primary_text_color") or "#FDFCFD")
    secondary = ass_color(cap.get("secondary_text_color")
                          or cap.get("primary_text_color") or "#FDFCFD")
    outline_color = ass_color(cap.get("outline_color") or "#0B090B")
    outline = max(0, int(round(float(poster.get("outline_width")
                                     or block_cfg.get("outline_width")
                                     or cap.get("outline_width") or 5) * scale)))
    shadow = outline + 2
    accent = poster.get("keyword_color") or "#FFFFFF"
    sticker_back = ass_color(str(poster.get("sticker_bg") or accent))

    sentences = segment_sentences(
        declutter(words),
        max_words=int(poster.get("max_words") or block_cfg.get("max_words") or 4),
        max_chars=int(poster.get("max_chars") or 30))

    events: list[str] = []
    blocks: list[dict] = []
    for i, sent in enumerate(sentences):
        hard_end = (float(sentences[i + 1][0].start) - 0.033
                    if i + 1 < len(sentences) else None)
        ev, bbox = _poster_events(sent, style, width=width, height=height,
                                  poster=poster, hard_end=hard_end)
        events.extend(ev)
        emph = pick_emphasis(sent)
        blocks.append({"start": round(float(sent[0].start), 3),
                       "end": round(float(sent[-1].end), 3),
                       "text": " ".join(str(w.text) for w in sent),
                       "emphasis": str(sent[emph].text),
                       "emphasis_at": round(float(sent[emph].start), 3),
                       "bbox": [round(v, 1) for v in bbox]})

    for card in cards or []:
        events.extend(_card_events(card, width=width, height=height,
                                   poster=poster))
    for sticker in stickers or []:
        events.extend(_sticker_events(sticker, width=width, height=height,
                                      poster=poster))
    for lst in lists or []:
        events.extend(_list_events(lst, width=width, height=height,
                                   poster=poster))

    _bs = float(poster.get("base_size_ass") or 88) * scale
    events.extend(build_hook_events(
        hook_lines or [], outro_text, width=width, height=height, end=end,
        base_size=_bs, emphasis_size=_bs * 1.5,
        accent=accent, typing=bool(poster.get("typing_hook", True))))
    if handle and end:
        events.append(f"Dialogue: 2,0:00:00.00,{fmt_ass(end)},Handle,,0,0,0,,"
                      f"{handle}")

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Poster,{font_name},{int(round(88 * scale))},{primary},{secondary},{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1
Style: Card,{font_name},{int(round(148 * scale))},{primary},{secondary},{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1
Style: Sticker,{font_name},{int(round(64 * scale))},{ass_color(str(poster.get('sticker_text') or '#101418'))},&H000000FF,{sticker_back},{sticker_back},-1,0,0,0,100,100,0,0,3,{max(8, outline)},0,7,0,0,0,1
Style: Hook,{font_name},{int(round(120 * scale))},{primary},{secondary},{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},8,0,0,0,1
Style: Handle,{font_name},{int(round(36 * scale))},&H59FFFFFF,&H000000FF,{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{max(1, outline // 2)},{shadow},3,{int(round(28 * scale))},{int(round(36 * scale))},{int(round(34 * scale))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return head + "\n".join(events) + "\n", blocks


def write_poster_ass(path: str | Path, words: list[Word], style: dict, **kw):
    text, blocks = build_poster_ass(words, style, **kw)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p, blocks
