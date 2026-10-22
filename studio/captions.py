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
                     hold: float = 0.06, min_hold: float = 0.18) -> list[dict]:
    """One card per 1-2 words, each held until its word stops sounding.

    The rule is the operator's, not a heuristic: a word stays on screen for as
    long as it is audible, plus a hair. Cutting a card on the next onset makes
    the last word of a phrase vanish while it is still being sung, which is the
    single most obvious tell that captions were generated rather than placed.

    Cards still tile with no gaps: a card may only run up to the next onset, never
    past it. Short words get `min_hold` so a card is never a single frame.
    """
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


def to_script(cards: list[dict], bpm: float, accent: dict | None = None) -> list[dict]:
    """Cards -> the script format compose.py reads (beats from frame one)."""
    accent = accent or {}
    out = []
    for c in cards:
        word = next((w for w in c["text"].split()
                     if w.lower().strip(",.?!") in accent), "")
        out.append({
            "beat": round(c["start"] * bpm / 60.0, 3),
            "text": c["text"],
            "accent": word.upper(),
            "pin": False,
            "matte": False,
            "until": round(c["end"] * bpm / 60.0, 3),
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
        card = render_card(c["text"], 1920, 1080)
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
