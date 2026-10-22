"""Captions in, cards out. The words are an input.

The workflow this implements:

    captions.txt  (the real lyric, one line per sung line)
        -> ASR gives the clock
        -> align() puts every word on a timestamp
        -> cards are cut from the WORD stream, not from the line
        -> a still-frame sheet of every card, for approval
        -> then, and only then, a render

Why cards come from the word stream: the reference overedit changes card every
16th in the drop — `ALL I NEED / IS A / BEAUTY / AND A / BEAT` — one or two words
at a time, each card outlasting its own word by a beat at most. A card that holds
a whole sung line for two seconds is a subtitle, not type as an instrument.

Nothing here invents a word. If the text file and the audio disagree badly, the
aligner's confidence drops and `coverage()` says so — which is a "check the text"
message, not something to paper over.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .lyrics import LyricWord, align_fuzzy, transcribe_robust

SECTION = re.compile(r"^\s*[\[(].*[\])]\s*$")     # [Chorus], (x2)

# The words a lyric turns on. An accent on every card is decoration; one accent
# per thought is design. Kept as data so a different song is a different list.
ACCENT_WORDS = {
    "beauty", "beat", "complete", "yours", "life", "need", "make", "young",
    "tonight", "coming", "cause", "music", "move", "baby", "do", "all", "you",
    "she", "her", "gwen", "stay", "gone", "love", "wait", "know",
}


# Words that carry weight, versus words that only connect. "YOU MOVE" accents
# MOVE; "IT'S ALL" accents ALL because there is nothing stronger on the card.
STRONG = {"beauty", "beat", "complete", "life", "need", "make", "tonight",
          "coming", "music", "move", "baby", "gwen", "love", "stay", "gone",
          "young", "yours", "cause", "know"}


def accent_word(text: str) -> str:
    """The one word on this card that gets the accent face and colour.

    Strong word first, connector second, nothing if the card has neither. A card
    with no accent is fine — accenting every card is decoration, not design.
    """
    words = [w.strip(",.'!?").upper() for w in text.split()]
    for w in words:
        if w.lower() in STRONG:
            return w
    for w in words:
        if w.lower() in ACCENT_WORDS:
            return w
    return ""


def parse_lines(path: str | Path) -> list[str]:
    """Read a caption file: one sung line per line of text.

    Timestamps are allowed and ignored — a line that starts with `00:12.480` or
    `[00:12.48]` keeps only its words, because the timing comes from the audio.
    Section markers and blank lines are dropped.
    """
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or SECTION.match(s):
            continue
        s = re.sub(r"^[\[(]?\d{1,2}:\d{2}[.:]\d{1,3}[\])]?\s*", "", s)
        s = re.sub(r"-->.*$", "", s).strip()
        # "It's all (all) 'bout you" — the bracket is an echo that IS sung, so the
        # word stays and only the bracket goes. Dropping it would shift every
        # word after it off its syllable.
        s = re.sub(r"[()\[\]]", "", s)
        if s:
            lines.append(s)
    return lines


def words_of(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        out.extend(line.split())
    return out


def cards_from_words(lines: list[str], track: str, start: float,
                     duration: float, max_words: int = 2,
                     hold: float = 0.06, min_hold: float = 0.18,
                     asr: list[dict] | None = None) -> list[dict]:
    """One card per 1-2 words, each held until its word stops sounding.

    The rule is the operator's, not a heuristic: a word stays on screen for as
    long as it is audible, plus a hair. Cutting a card on the next onset makes
    the last word of a phrase vanish while it is still being sung, which is the
    single most obvious tell that captions were generated rather than placed.

    Cards still tile with no gaps: a card may only run up to the next onset, never
    past it. Short words get `min_hold` so a card is never a single frame.
    """
    if asr is None:
        asr = transcribe_robust(track, start, duration)
    placed = align_fuzzy(lines, asr)

    # Monotonic, always. Two words that both missed the recogniser come back
    # interpolated to the same instant, which puts two cards on one frame and
    # makes a 0.09s card between them. Push each word past the one before it.
    for line in placed:
        prev_end = None
        for w in line.words:
            if prev_end is not None and w.start < prev_end + 0.04:
                shift = prev_end + 0.04 - w.start
                w.start += shift
                w.end = max(w.end + shift, w.start + 0.04)
            prev_end = w.end

    # Chunk WITHIN a line. A card that straddles two sung lines reads as a
    # caption generator that has lost its place.
    chunks: list[dict] = []
    for li, line in enumerate(placed):
        ws = line.words
        for i in range(0, len(ws), max_words):
            part = ws[i:i + max_words]
            chunks.append({"text": " ".join(w.text for w in part),
                           "start": part[0].start,
                           "end_of_words": part[-1].end,
                           "conf": min(w.confidence for w in part),
                           # which SUNG LINE this card belongs to. Direction is
                           # written per line, so a card has to know its parent.
                           "line": li})
    if not chunks:
        return []

    cards = []
    for i, c in enumerate(chunks):
        t0 = c["start"]
        # hold until the card's LAST word stops sounding
        t1 = max(c["end_of_words"] + hold, t0 + min_hold)
        if i + 1 < len(chunks):
            nxt = chunks[i + 1]["start"]
            if nxt < t1:
                # the next word starts before this one has finished: never run
                # into the next card, so the card stops at that onset
                t1 = nxt
        cards.append({"start": round(t0, 3),
                      "end": round(max(t1, t0 + min_hold * 0.5), 3),
                      # confidence of the worst word in the card, so a badly
                      # aligned line is visible in the preview instead of shipping
                      "text": c["text"], "conf": round(c["conf"], 2),
                      "line": c["line"]})
    return cards


# ---------------------------------------------------------------------------
# Two caption conventions that are not about accuracy, but decide whether the
# words FEEL right. Both were learned from watching a delivered edit back.
#
#   LEAD  type arrives a beat before the syllable. A caption that lands exactly
#         on the attack reads late, because the eye needs ~0.2s to arrive and
#         the ear is already past the word. Karaoke has done this for decades.
#
#   TILE  a gap shorter than TILE inside a sung passage is not silence, it is a
#         breath or a held note — and a card that vanishes there looks like the
#         caption system lost its place. Hold the previous card through it. A
#         real instrumental break (this track has a 5.3s one) is longer than
#         TILE and is left alone: type across an instrumental is a lie about
#         where the voice is.
# ---------------------------------------------------------------------------
LEAD = 0.15          # type arrives a beat before the syllable
TAIL = 0.42          # how long a word keeps holding after its audio stops
GAP = 1.80           # a hole longer than this is an instrumental: leave it bare
MIN_CARD = 0.45      # shorter than this is a flash, not a word
MAX_MERGE = 3        # a merged card never carries more words than this
FINAL_TAIL = 1.10    # the last card leaves with the music, not before it
MAX_HOLD = 3.60      # a card on screen longer than this has become furniture


def polish(cards: list[dict], lead: float = LEAD, tail: float = TAIL,
           gap: float = GAP, min_card: float = MIN_CARD,
           max_merge: int = MAX_MERGE, final_tail: float = FINAL_TAIL) -> list[dict]:
    """One rule: a card stays until the next word arrives.

    Every earlier attempt at this had two authorities — the word's own audio and
    a cap on how long a card may sit — and they fought, which is why the same
    complaint came back in a different place each time. Here the card's length is
    the distance to the next onset and nothing else:

        start = onset - LEAD          (type leads the syllable by a hair)
        end   = next card's start     (held, not re-timed)

    so a card is on screen for exactly as long as its word is the current word,
    and card durations stop being arbitrary. Two exceptions, both of them about
    the music rather than the mechanism:

      * a hole longer than GAP is an instrumental, not a breath. The word holds
        for TAIL and then the picture is bare — type over an instrumental is a
        lie about where the voice is;
      * two words closer together than MIN_CARD cannot both be read. They become
        one card if they fit, otherwise the second is nudged out by MIN_CARD.

    The last card gets FINAL_TAIL: a lyric that vanishes while the chord is still
    ringing is the one place a viewer notices the captions ending.
    """
    src = sorted((dict(c) for c in cards), key=lambda c: c["start"])

    # 1. flashes: two onsets this close cannot be two cards
    merged: list[dict] = []
    for c in src:
        if merged and (c["start"] - merged[-1]["start"]) < min_card:
            words = (merged[-1]["text"] + " " + c["text"]).split()
            if len(words) <= max_merge:
                merged[-1]["text"] = " ".join(words)
                merged[-1]["end"] = max(merged[-1]["end"], c["end"])
                continue
            c = {**c, "start": merged[-1]["start"] + min_card}
        merged.append(dict(c))

    # 2. lead in
    for c in merged:
        c["start"] = max(0.0, c["start"] - lead)

    # 3. hold until the next word
    for i, c in enumerate(merged):
        held = c["end"] + (final_tail if i == len(merged) - 1 else tail)
        nxt = merged[i + 1]["start"] if i + 1 < len(merged) else None
        if nxt is not None and (nxt - c["end"]) <= gap:
            c["end"] = max(nxt, c["start"] + min_card)
        else:
            c["end"] = max(held, c["start"] + min_card)
        c["start"] = round(c["start"], 3)
        c["end"] = round(c["end"], 3)
    return merged


def save_cards(cards: list[dict], path: str | Path) -> Path:
    """Write a card table that knows it has already been polished.

    Every second pass through polish() is damage: LEAD applied twice moves the
    type a third of a second early, and the final tail doubles. The marker is
    how produce tells the difference between "a table" and "an approved table".
    """
    import json

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"polished": True, "cards": cards}, indent=1) + "\n")
    return p


def lint(cards: list[dict], gap: float = GAP, min_card: float = MIN_CARD,
         max_hold: float = MAX_HOLD) -> list[str]:
    """What would a viewer notice? Every line here is a complaint waiting to happen."""
    bad: list[str] = []
    for a, b in zip(cards, cards[1:]):
        hole = b["start"] - a["end"]
        if hole < -0.001:
            bad.append(f"overlap {hole:+.2f}s at {a['text']!r} -> {b['text']!r}")
        elif 0.0 < hole <= gap:
            bad.append(f"hole {hole:.2f}s at {a['text']!r} -> {b['text']!r}")
    for c in cards:
        d = c["end"] - c["start"]
        if d < min_card - 1e-6:
            bad.append(f"flash {d:.2f}s on {c['text']!r}")
        elif d > max_hold:
            bad.append(f"held {d:.2f}s on {c['text']!r}")
    return bad


def timeline(cards: list[dict]) -> str:
    """The card table as a viewer experiences it: time, length, gap to the next."""
    rows = ["    start     end   len  gap  text"]
    for i, c in enumerate(cards):
        gap = (cards[i + 1]["start"] - c["end"]) if i + 1 < len(cards) else 0.0
        rows.append(f"  {c['start']:7.2f} {c['end']:6.2f} {c['end'] - c['start']:5.2f}"
                    f" {gap:4.2f}  {c['text']}")
    return "\n".join(rows)


TIMED = re.compile(
    r"^\s*[\[(]?(\d{1,2}):(\d{2}(?:[.:]\d{1,3})?)[\])]?"
    r"(?:\s*(?:-|–|-->)\s*(\d{1,2}):(\d{2}(?:[.:]\d{1,3})?))?\s*(.+)$")


def parse_timed(path: str | Path) -> list[tuple[float, float | None, str]]:
    """Read a lyric whose lines carry their own times.

        [00:28.230] we young tonight
        00:38.840 - 00:43.600  Is a beauty and a beat

    A start is enough (the line runs to the next one). An end is better where a
    line crosses an instrumental, and is the only reliable option when the mix
    is too dense for the energy trim to find the voice.
    """
    out: list[tuple[float, float | None, str]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or SECTION.match(s):
            continue
        m = TIMED.match(s)
        if not m:
            continue
        at = int(m.group(1)) * 60 + float(m.group(2).replace(":", "."))
        end = None
        if m.group(3) is not None:
            end = int(m.group(3)) * 60 + float(m.group(4).replace(":", "."))
        text = re.sub(r"[()\[\]]", "", m.group(5)).strip()
        if text:
            out.append((round(at, 3), None if end is None else round(end, 3), text))
    out.sort(key=lambda r: r[0])
    return out


def from_timed(track: str | Path, timed: list[tuple[float, float | None, str]],
               duration: float,
               max_words: int = 2, hold: float = 0.06,
               min_hold: float = 0.18) -> list[dict]:
    """Place a lyric that already knows where its LINES start.

    This is the path for a song the recogniser cannot read at all — anything not
    in English, and any mix where the vocal is buried. It needs no transcript:
    each line's start is given, and the words inside it are distributed over the
    sung span and snapped to syllable nuclei, which are language-independent.

    A line's span runs to the next line's start, so the operator's own line
    breaks are the anchor and nothing has to be inferred from the words.
    """
    import imageio_ffmpeg

    from clipper.align.energy_align import align_words

    import subprocess

    import numpy as np

    ff = imageio_ffmpeg.get_ffmpeg_exe()

    tmp = "/tmp/studio_timed.raw"
    subprocess.run([ff, "-nostdin", "-y", "-v", "error", "-i", str(track),
                    "-ac", "1", "-ar", "16000", "-f", "s16le", tmp], check=True)
    audio = np.fromfile(tmp, dtype=np.int16).astype(np.float32) / 32768.0
    rate = 16000

    # A line's span runs to the next line's start, which is generous: the last
    # line before an instrumental would otherwise spread its words across the
    # silence. Trim each span to where the voice actually is, then align inside
    # what is left. Energy, not language — this works on a Hindi or Bangla vocal
    # exactly as it does on an English one.
    env = np.abs(audio)
    k = max(1, int(0.05 * rate))
    env = np.convolve(env, np.ones(k) / k, mode="same")

    def sung(a: float, b: float) -> tuple[float, float]:
        i0, i1 = int(max(0.0, a) * rate), int(min(len(audio), b * rate))
        if i1 - i0 < rate * 0.2:
            return a, b
        seg = env[i0:i1]
        thr = 0.30 * float(seg.max() or 1.0)
        on = np.flatnonzero(seg > thr)
        if on.size == 0:
            return a, b
        return (max(a, i0 / rate + on[0] / rate - 0.10),
                min(b, i0 / rate + on[-1] / rate + 0.30))

    chunks: list[dict] = []
    for i, (at, given_end, text) in enumerate(timed):
        nxt = timed[i + 1][0] if i + 1 < len(timed) else min(duration, at + 6.0)
        end = given_end if given_end else nxt
        if given_end is None:
            at, end = sung(at, end)
        words = align_words(text, audio, rate, t0=0.0, intervals=[(at, end)])
        if not words:
            continue
        for k in range(0, len(words), max_words):
            part = words[k:k + max_words]
            chunks.append({"text": " ".join(w.text for w in part),
                           "start": part[0].start, "end_of_words": part[-1].end,
                           "conf": 1.0, "line": i})
    cards = []
    for i, c in enumerate(chunks):
        t0 = c["start"]
        t1 = max(c["end_of_words"] + hold, t0 + min_hold)
        if i + 1 < len(chunks) and chunks[i + 1]["start"] < t1:
            t1 = chunks[i + 1]["start"]
        cards.append({"start": round(t0, 3),
                      "end": round(max(t1, t0 + min_hold * 0.5), 3),
                      "text": c["text"], "conf": c["conf"], "line": c["line"]})
    return cards


def coverage(cards: list[dict], lines: list[str]) -> dict:
    want = words_of(lines)
    got = " ".join(c["text"] for c in cards).split()
    low = [c["text"] for c in cards if c["conf"] < 0.6]
    return {
        "words_in_text": len(want),
        "words_on_screen": len(got),
        "matches": want == got,
        "unplaced": [w for w in want if w not in got],
        "low_confidence_cards": low,
        "cards": len(cards),
        "span": [cards[0]["start"], cards[-1]["end"]] if cards else [0, 0],
    }


def lines_of(cards: list[dict]) -> list[dict]:
    """Group cards into the sung lines they came from: [start, end, cards]."""
    out: list[dict] = []
    for c in cards:
        if out and out[-1]["line"] == c["line"]:
            out[-1]["end"] = c["end"]
            out[-1]["cards"].append(c)
        else:
            out.append({"line": c["line"], "start": c["start"],
                        "end": c["end"], "cards": [c]})
    return out


def to_script(cards: list[dict], bpm: float, accent: dict | None = None,
              origin: float = 0.0) -> list[dict]:
    """Cards -> the script format compose.py reads (beats from frame one).

    `origin` is the track time where the edit begins. Cards are placed against
    the track (25.98s means 25.98s into the song), the picture is placed against
    the edit (frame one = the start of the window), and compose counts beats from
    frame one. Without the subtraction a card approved at 25.98s into the song
    lands 23.83 seconds late in a window that starts there — the words arrive
    after the line has been sung, over the wrong shots.
    """
    accent = accent or ACCENT_WORDS
    out = []
    for c in cards:
        word = accent_word(c["text"])
        out.append({
            "beat": round((c["start"] - origin) * bpm / 60.0, 3),
            "text": c["text"],
            "line": c.get("line", -1),
            "accent": word.upper(),
            "pin": False,
            "matte": False,
            "until": round((c["end"] - origin) * bpm / 60.0, 3),
        })
    return out


def preview(cards: list[dict], out: str | Path, video: str | Path | None = None,
            cols: int = 4, tile_w: int = 460) -> Path:
    """A still of every card, on the real plate, before committing to a render.

    The point is approval: words, timing and legibility are decided here, not
    after four minutes of encoding.
    """
    import subprocess

    import imageio_ffmpeg
    from PIL import Image, ImageDraw

    from . import fonts
    from .typecards import composite, render_card, scrim

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tiles = []
    for i, c in enumerate(cards):
        mid = (c["start"] + c["end"]) / 2.0
        if video and Path(video).exists():
            f = f"/tmp/cap_{i}.png"
            subprocess.run([ff, "-loglevel", "error", "-y", "-ss", f"{mid:.3f}",
                            "-i", str(video), "-frames:v", "1", f], check=True)
            frame = Image.open(f).convert("RGB")
        else:
            frame = Image.new("RGB", (1920, 1080), (18, 18, 20))
        card = render_card(c["text"], 1920, 1080,
                           accent=accent_word(c["text"]) or None,
                           cap_frac=fonts.cap_frac())
        import numpy as np

        arr = np.asarray(frame).copy()
        scrim(arr, card, amount=0.34, blur=12)
        composite(arr, card)
        im = Image.fromarray(arr).resize((tile_w, int(tile_w * 9 / 16)))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 150, 26], fill=(0, 0, 0))
        d.text((6, 7), f"{c['start']:.2f}s  {c['end']-c['start']:.2f}s",
               fill=(255, 220, 0))
        tiles.append(im)

    rows = (len(tiles) + cols - 1) // cols
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * cols, h * rows), (0, 0, 0))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % cols) * w, (k // cols) * h))
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(p, quality=90)
    return p


def build(text_path: str | Path, track: str, start: float, duration: float,
          bpm: float, script_path: str | Path,
          preview_path: str | Path | None = None,
          video: str | Path | None = None,
          max_words: int = 2, accent: dict | None = None) -> dict:
    lines = parse_lines(text_path)
    cards = cards_from_words(lines, track, start, duration, max_words)
    script = to_script(cards, bpm, accent)
    p = Path(script_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"cards": script}, indent=1) + "\n")
    cov = coverage(cards, lines)
    if preview_path:
        preview(cards, preview_path, video)
    return cov
