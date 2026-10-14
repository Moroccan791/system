"""Sentence-block captions: the professional look from the tutorial recipe.

The unit is the sentence, not the word, and three rules make it read as
professional rather than amateur:

1. Words reveal exactly when spoken and *stay* until the sentence clears, so
   the eye is assembling a sentence block instead of reading single flashes.
2. The operative word of the sentence is bigger than its connectives ("one
   word will be slightly bigger and the other words will remain smaller").
3. Every word does the same motion: a small rise with an ease-out fade. The
   polish is the consistency.

libass cannot karaoke-reveal words inside one dialogue without ghost outlines
(pre-reveal syllables keep the line's outline), so instead the layout is done
here, in pixels, and each word is its own event at its computed position. The
same pass draws the "bottom fade bar": a black gradient ramp along the caption
zone ("This is where our captions will appear"), which is what makes white
text sit down on any footage.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..asr.base import Word
from .ass import ass_color, fmt_ass

# fragments of speech that never deserve the big treatment
STOPWORDS = frozenset(
    """the a an and or but if then than so of in on at to for with from by as is are
    was were be been being do does did done have has had having you your youre he she
    it its they them their we our us i me my him her his what when where who whom how
    why that this these those there here yeah yes no not okay ok uh um like just really
    very too also into out up down over under after before about can could would should
    will shall may might must said say says ask asked talk talks guys hey oh ah right
    well now one two three get got go goes getting coming come comes make makes made know
    think thing things let lets look kind little much many every goes way""".split()
)

# relative advance widths for Montserrat-ish heavy sans, as a fraction of the
# font size; per-character overrides for the outliers
NARROW = set("ijlft.,'!|;:[]()I")
NARROWER = set(" ")
WIDE = set("mwMW@%")
WIDE_CAPS = set("ABCDEFGHKMNOPQRSTUVXWY")

NUMBER_WORDS = frozenset("""zero one two three four five six seven eight nine ten eleven
    twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty
    forty fifty sixty seventy eighty ninety hundred thousand million billion half quarter
    third fourth fifth percent percentage""".split())

SENTENCE_END = (".", "?", "!", "…")


def _text_width(word: str, size: float) -> float:
    """Rough advance width in pixels for a heavy sans at `size` ASS px.

    The layout only needs *relative* correctness - centre-alignment and
    inter-word spacing - and at 1080px wide an error of 2-3px reads as kinetic
    rather than wrong.
    """
    width = 0.0
    for ch in word:
        if ch in NARROW:
            width += 0.34
        elif ch in NARROWER:
            width += 0.30
        elif ch in WIDE:
            width += 0.98
        elif ch in WIDE_CAPS:
            width += 0.82
        elif ch.isdigit():
            width += 0.66
        elif ch.isupper():
            width += 0.76
        else:
            width += 0.63
    # Montserrat ExtraBold + outline run wider than the table: the first
    # real render clipped "All" to "ll" at the frame edge. Err wide.
    return width * size * 1.10


def declutter(words: list[Word]) -> list[Word]:
    """One speaker at a time: drop words that talk over the previous word.

    Moonshine-style ASR weaves simultaneous speakers into a single stream
    ("No Don't I You Sometimes Apparently" - six words, one timestamp, two
    people). Captioning both streams at once is how blocks turn to junk.
    Greedy by start: a word that begins well inside the previous kept word
    belongs to the other voice; the dominant speaker's words tile the time
    and survive. Words landing in genuine pauses (reactions, "yeah") stay -
    they are audible and honest.
    """
    kept: list[Word] = []
    last_end = -1e9
    for w in sorted(words, key=lambda w: float(w.start)):
        if float(w.start) >= last_end - 0.08:
            kept.append(w)
            last_end = max(last_end, float(w.end))
    return kept


def segment_sentences(words: list[Word], *, max_words: int = 10, max_chars: int = 52,
                      break_gap: float = 1.0) -> list[list[Word]]:
    """Cut the transcript into caption blocks at sentence ends and real pauses.

    A block that outgrows max_words/max_chars is forced closed: blocks are for
    reading, not for hoarding.
    """
    sentences: list[list[Word]] = []
    current: list[Word] = []
    n_chars = 0
    for w in words:
        text = str(w.text)
        if current and float(w.start) - float(current[-1].end) > break_gap:
            sentences.append(current)
            current, n_chars = [], 0
        current.append(w)
        n_chars += len(text)
        if text.rstrip().endswith(SENTENCE_END):
            sentences.append(current)
            current, n_chars = [], 0
        elif len(current) >= max_words or n_chars >= max_chars:
            sentences.append(current)
            current, n_chars = [], 0
    if current:
        sentences.append(current)
    return sentences


def pick_emphasis(sentence: list[Word]) -> int:
    """Which word gets the big treatment: the most content-bearing one.

    Length is the signal (stop words are filtered first), with a bias toward
    the back half of the block - the operative word usually *lands* at the end
    of a sentence, it does not open it.
    """
    best, best_score = 0, -1.0
    for i, w in enumerate(sentence):
        token = re.sub(r"[^\w']+", "", str(w.text)).lower()
        score = float(len(token))
        if token in STOPWORDS:
            score *= 0.15
        if i >= (len(sentence) - 1) // 2:
            score *= 1.25           # late words carry the point more often
        if re.search(r"\d", token) or token in NUMBER_WORDS:
            score *= 1.7            # numbers are never filler, digits or spelled out
        if score > best_score:
            best, best_score = i, score
    return best


def _wrap(sentence: list[Word], emphasis: int, sizes: list[float], *,
          max_width: float) -> list[list[int]]:
    """Paint words onto display lines no wider than max_width (pixels).

    The emphasis word owns its line unless it is the sentence's only long word,
    because a big word squeezed beside small ones is how amateur edits look -
    the tutorial blocks give the operative word the row. Word order is never
    rearranged: a caption that swaps two words is worse than a wide line.
    """
    space = sizes[0] * 0.30
    rows: list[list[int]] = []
    current: list[int] = []
    for i in range(len(sentence)):
        word_w = _text_width(str(sentence[i].text), sizes[i])
        own_line = (i == emphasis and len(sentence) > 1)
        if own_line:
            if current:
                rows.append(current)
            rows.append([i])
            current = []
            continue
        used = sum(_text_width(str(sentence[j].text), sizes[j]) for j in current) \
            + space * len(current) if current else 0.0
        if current and used + word_w > max_width:
            rows.append(current)
            current = [i]
        else:
            current.append(i)
    if current:
        rows.append(current)
    return rows


def _layout_rows(sentence: list[Word], emphasis: int, sizes: list[float],
                 max_width: float) -> list[list[int]]:
    rows = _wrap(sentence, emphasis, sizes, max_width=max_width)
    # at most 3 rows: merge the narrowest neighbours until it fits
    while len(rows) > 3:
        widths = [sum(_text_width(str(sentence[j].text), sizes[j]) for j in r)
                  for r in rows]
        i = min(range(len(rows)), key=lambda k: widths[k])
        if i == 0:
            rows[1] = rows[0] + rows[1]
            rows.pop(0)
        else:
            rows[i - 1] = rows[i - 1] + rows[i]
            rows.pop(i)
    return rows


def _sentence_events(sentence: list[Word], style: dict, *, width: int, height: int,
                     block: dict, hard_end: float | None = None) -> list[str]:
    cap = style.get("captions", {}) or {}
    scale = height / 1920.0
    base_size = float(block.get("base_size_ass") or 84) * scale
    emphasis_size = base_size * float(block.get("emphasis_scale") or 1.6)
    rise_px = float(block.get("rise_px") or 16) * scale
    rise_ms = int(block.get("rise_ms") or 250)
    fade_ms = int(block.get("fade_in_ms") or 120)
    wipe_ms = max(1, int(block.get("word_wipe_ms") or 90))
    casing = (block.get("emphasis_case") or "title").lower()
    margin_v = float((cap.get("position") or {}).get("margin_v") or 420) * scale

    emphasis = pick_emphasis(sentence)
    sizes = [emphasis_size if i == emphasis else base_size for i in range(len(sentence))]

    max_width = width - 2 * (width * 0.07)

    def _widest(ls):
        return max((sum(_text_width(str(sentence[i].text), sizes[i]) for i in line)
                    + (len(line) - 1) * base_size * 0.30) for line in ls)

    lines = _layout_rows(sentence, emphasis, sizes, max_width)
    # shrink until every row truly fits: _layout_rows caps at 3 rows by
    # merging, and a merged row can be wider than the frame - type that
    # runs off the edge is the loudest amateur tell there is
    while (len(lines) > 3 or _widest(lines) > max_width) and base_size > 34:
        base_size *= 0.92
        emphasis_size = base_size * float(block.get("emphasis_scale") or 1.6)
        sizes = [emphasis_size if i == emphasis else base_size for i in range(len(sentence))]
        lines = _layout_rows(sentence, emphasis, sizes, max_width)

    line_heights = [max(sizes[i] for i in line) * 1.22 for line in lines]
    block_h = sum(line_heights)
    top = height - margin_v - block_h

    start = float(sentence[0].start)
    end = float(sentence[-1].end) + float(block.get("clear_after") or 0.35)
    if hard_end is not None:
        end = min(end, max(float(sentence[-1].end) + 0.08, hard_end))

    events: list[str] = []
    y_acc = top
    for li, line in enumerate(lines):
        line_h = line_heights[li]
        line_max = max(sizes[i] for i in line)
        space = base_size * 0.30
        line_w = sum(_text_width(str(sentence[i].text), sizes[i]) for i in line) \
            + (len(line) - 1) * space
        x = max(6.0, (width - line_w) / 2.0)
        for i in line:
            w = sentence[i]
            text = _escape(str(w.text))
            size = sizes[i]
            display = str(w.text)
            if i == emphasis:
                if casing == "upper":
                    display = display.upper()
                elif casing == "title" and display[:1].islower():
                    display = display[:1].upper() + display[1:]
            text = _escape(display)
            # baseline align: the top of *this* word sits below a taller neighbour's
            y = y_acc + (line_max - size) * 0.75
            tags = (rf"\pos({x:.1f},{y:.1f})"
                    rf"\fs{size:.0f}"
                    rf"\fad({fade_ms},0)"
                    rf"\move({x:.1f},{y + rise_px:.1f},{x:.1f},{y:.1f},0,{rise_ms})")
            events.append(f"Dialogue: 1,{fmt_ass(float(w.start))},{fmt_ass(end)},"
                          f"Block,,0,0,0,,{{{tags}}}{text}")
            x += _text_width(display, size) + space
        y_acc += line_h

    pad = float(block.get("clear_after") or 0.35)
    events.append(f"# block {fmt_ass(start)}-{fmt_ass(end)} pad={pad:.2f}")
    return events


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_fade_bar(width: int, height: int, *, alpha: float = 0.55,
                   zone: float | None = None, strips: int = 18,
                   end: float | None = None) -> list[str]:
    """The bottom fade bar as thin ASS vector strips, strongest at the bottom.

    Rendered as separate events because one drawing cannot vary its alpha
    along its height. Layer 0, beneath the caption layer.
    """
    zone = float(zone or height * 0.30)
    top = height - zone
    strip_h = zone / strips
    tail = fmt_ass(end) if end else "9:59:59.00"
    events: list[str] = []
    for i in range(strips):
        # alpha ramps 0 at the zone's top to `alpha` at the bottom of the frame
        a = min(1.0, (alpha * (i + 1) / strips))
        aa = int(round((1.0 - a) * 255))      # ASS alpha: 0 opaque .. 255 hidden
        y0, y1 = top + i * strip_h, top + (i + 1) * strip_h + 1.0
        draw = (rf"m 0 {y0:.1f} l {width} {y0:.1f} l {width} {y1:.1f} l 0 {y1:.1f}")
        events.append(f"Dialogue: 0,0:00:00.00,{tail},Bar,,0,0,0,,"
                      rf"{{\an7\pos(0,0)\1a&H{aa:02X}&\p1}}{draw}{{\p0}}")
    return events


def build_block_ass(words: list[Word], style: dict, *, width: int = 1080,
                    height: int = 1920, end: float | None = None) -> tuple[str, list[dict]]:
    """A complete .ass script in block mode, plus the block list it encodes."""
    cap = style.get("captions", {}) or {}
    block = cap.get("block", {}) or {}
    scale = height / 1920.0
    font_name = cap.get("font_name") or "Montserrat"
    primary = ass_color(cap.get("primary_text_color") or "#FDFCFD")
    secondary = ass_color(cap.get("secondary_text_color") or cap.get("primary_text_color")
                          or "#FDFCFD")
    outline_color = ass_color(cap.get("outline_color") or "#0B090B")
    outline = max(0, int(round(float(block.get("outline_width")
                                            or cap.get("outline_width") or 4) * scale)))
    shadow = max(outline + 1, int(round(float(block.get("shadow")
                                                     or max(2, float(cap.get("shadow") or 0))) * scale)))

    sentences = segment_sentences(declutter(words),
                                  max_words=int(block.get("max_words") or 10),
                                  max_chars=int(block.get("max_chars") or 52))
    events: list[str] = []
    blocks: list[dict] = []
    if block.get("fade_bar", True):
        # the bar belongs where the text is: from above the tallest common
        # block (2.4 rows of emphasis-sized type) down through the margin
        margin_v = float((cap.get("position") or {}).get("margin_v") or 420) * scale
        emph = float(block.get("base_size_ass") or 84) * scale * \
            float(block.get("emphasis_scale") or 1.6)
        zone = margin_v + emph * 1.22 * 2.4 + 40 * scale
        events.extend(build_fade_bar(width, height,
                                     alpha=float(block.get("fade_bar_alpha") or 0.55),
                                     zone=zone, end=end))
    for i, sent in enumerate(sentences):
        emph = pick_emphasis(sent)
        # a block must yield its screen the moment the next one starts: two
        # blocks stacked on the same rows read as a rendering bug, not a style
        hard_end = float(sentences[i + 1][0].start) - 0.033 if i + 1 < len(sentences) else None
        events.extend(_sentence_events(sent, style, width=width, height=height,
                                       block=block, hard_end=hard_end))
        blocks.append({"start": round(float(sent[0].start), 3),
                       "end": round(float(sent[-1].end), 3),
                       "text": " ".join(str(w.text) for w in sent),
                       "emphasis": str(sent[emph].text)})

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Block,{font_name},{int(round(84 * scale))},{primary},{secondary},{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},7,0,0,0,1
Style: Bar,Arial,10,&H007D7D7D,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return head + "\n".join(e for e in events if not e.startswith("#")) + "\n", blocks


def write_block_ass(path: str | Path, words: list[Word], style: dict, *,
                    width: int = 1080, height: int = 1920,
                    end: float | None = None) -> tuple[Path, list[dict]]:
    text, blocks = build_block_ass(words, style, width=width, height=height, end=end)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p, blocks
