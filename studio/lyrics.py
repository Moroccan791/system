"""Real lyric timing — captions that say what the song says, when it says it.

The failure this replaces: cards authored by hand on a beat grid, carrying words
that were not in the song. On screen that reads as subtitles for the WRONG film,
and it is the fastest way to lose a viewer who knows the track.

Method. ASR the track, then align a known lyric text to the ASR word stream with
a sequence match. Singing wrecks the ASR's words — it heard "I'm bloody and I'm
beat" for "a beauty and a beat" — but it gets the WORD COUNT and the TIMING
right for a sustained vocal, which is all an aligner needs. So:

    ASR words   -> timings, but wrong words
    lyric text  -> right words, but no timings
    alignment   -> right words at the right times

Words the ASR missed entirely are interpolated between their neighbours, so a
card never jumps or leaves a gap.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .sound import check_on_grid  # noqa: F401  (re-exported for callers)


def _norm(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


@dataclass
class LyricWord:
    text: str
    start: float
    end: float
    confidence: float = 1.0     # 1.0 = matched an ASR word, <1 = interpolated


@dataclass
class LyricLine:
    text: str
    words: list[LyricWord]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    def as_dict(self):
        return {"text": self.text, "start": round(self.start, 3),
                "end": round(self.end, 3),
                "words": [{"text": w.text, "start": round(w.start, 3),
                           "end": round(w.end, 3),
                           "conf": round(w.confidence, 2)} for w in self.words]}


def transcribe(track: str, start: float, duration: float,
               tmp: str = "/tmp/lyric_asr.wav") -> list[dict]:
    """ASR the track segment. Returns [{text,start,end}] on the SEGMENT clock."""
    import imageio_ffmpeg

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error",
                    "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", track,
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", tmp],
                   check=True)
    out = "/tmp/lyric_asr.json"
    done = subprocess.run([sys.executable, "-m", "clipper", "transcribe", tmp,
                           "--asr", "moonshine", "--out", out],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-800:])
    data = json.loads(Path(out).read_text())
    words = data.get("words", data) if isinstance(data, dict) else data
    return [{"text": str(w["text"]).strip(),
             "start": float(w["start"]), "end": float(w["end"])}
            for w in words if str(w.get("text", "")).strip()]


def align(lines: list[str], asr: list[dict]) -> list[LyricLine]:
    """Put the real lyric words on the ASR's clock."""
    if not asr:
        return []
    lyric_words: list[str] = []
    owner: list[int] = []
    for li, line in enumerate(lines):
        for w in line.split():
            lyric_words.append(w)
            owner.append(li)

    a = [_norm(w["text"]) for w in asr]
    b = [_norm(w) for w in lyric_words]

    # anchor lyric index -> asr index
    anchors: dict[int, int] = {}
    sm = difflib.SequenceMatcher(a=b, b=a, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal", "replace"):
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                anchors[i1 + k] = j1 + k

    out: list[LyricWord] = []
    for i, word in enumerate(lyric_words):
        if i in anchors:
            w = asr[anchors[i]]
            out.append(LyricWord(word, w["start"], w["end"], 1.0))
        else:
            # interpolate between the nearest anchors
            prev = max((k for k in anchors if k < i), default=None)
            nxt = min((k for k in anchors if k > i), default=None)
            if prev is not None and nxt is not None:
                t0 = asr[anchors[prev]]["end"]
                t1 = asr[anchors[nxt]]["start"]
                frac = (i - prev) / max(1, (nxt - prev))
                t = t0 + (t1 - t0) * frac
            elif prev is not None:
                t = asr[anchors[prev]]["end"] + 0.22 * (i - prev)
            elif nxt is not None:
                t = asr[anchors[nxt]]["start"] - 0.22 * (nxt - i)
            else:
                t = 0.0
            out.append(LyricWord(word, t, t + 0.22, 0.4))

    # group back into lines
    result: list[LyricLine] = []
    for li, line in enumerate(lines):
        ws = [w for w, o in zip(out, owner) if o == li]
        if ws:
            result.append(LyricLine(line, ws))
    return result


def _sim(a: str, b: str) -> float:
    """How much two words sound like the same word, 0..1.

    Singing does not produce wrong words, it produces the right syllables through
    a bad recogniser: "beauty" comes back "bloody", "a" comes back "I'm". Exact
    matching then prefers a VERSE where the lyric happens to use plain words over
    the chorus where it is actually sung. So similarity, not equality:

      * identical -> 1.0
      * same opening sound and a similar shape -> most of the way there
      * one word is a prefix of the other ("i" / "i'm") -> 0.8
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if a[0] == b[0]:
        r = min(0.95, r + 0.15)
    if len(a) > 1 and len(b) > 1 and (a.startswith(b) or b.startswith(a)):
        r = max(r, 0.8)
    return r


def align_fuzzy(lines: list[str], asr: list[dict], min_sim: float = 0.62,
                gap: float = -0.30) -> list[LyricLine]:
    """Align the WHOLE lyric to the ASR stream at once, by sound.

    Global on purpose. Every line is scored against every position, but the
    sequence has to stay in order, so a repeated hook cannot drag a line into the
    second chorus and an instrumental gap cannot absorb half a phrase: the DP
    pays for the gap. The earlier per-line version searched independently and
    happily put "All I need is a beauty and a beat" on a verse, because the ASR
    had mangled the chorus and the verse had cleaner words.
    """
    toks, owner = [], []
    for li, line in enumerate(lines):
        for w in line.split():
            toks.append(_norm(w))
            owner.append(li)
    if not toks or not asr:
        return []

    an = [_norm(w["text"]) for w in asr]
    n, m = len(toks), len(an)
    NEG = -1e9
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]

    def match(i, j):
        sim = _sim(toks[i - 1], an[j - 1])
        return (sim, 2) if sim >= min_sim else (gap, 1)     # 2=match 1=skip-both

    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + gap
        back[i][0] = 1
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] + gap
        back[0][j] = 3

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sc, op = match(i, j)
            diag = score[i - 1][j - 1] + sc
            up = score[i - 1][j] + gap          # lyric word with no ASR word
            left = score[i][j - 1] + gap        # ASR word that is not ours
            best, how = diag, op
            if up > best:
                best, how = up, 1
            if left > best:
                best, how = left, 3
            score[i][j] = best
            back[i][j] = how

    i, j = n, m
    pairs: dict[int, tuple[int, float]] = {}
    while i > 0 and j > 0:
        how = back[i][j]
        if how == 2:
            pairs[i - 1] = (j - 1, _sim(toks[i - 1], an[j - 1]))
            i, j = i - 1, j - 1
        elif how == 1:
            i -= 1
        else:
            j -= 1

    step = 0.33
    out: list[LyricLine] = []
    for li, line in enumerate(lines):
        idx = [k for k, o in enumerate(owner) if o == li]
        if not idx:
            continue
        words: list[LyricWord] = []
        for k in idx:
            text = toks[k]
            raw = line.split()[k - idx[0]]
            if k in pairs:
                j, conf = pairs[k]
                words.append(LyricWord(raw, asr[j]["start"], asr[j]["end"],
                                       round(conf, 2)))
            else:
                prev = max((x for x in idx if x < k and x in pairs), default=None)
                nxt = min((x for x in idx if x > k and x in pairs), default=None)
                if prev is not None and nxt is not None:
                    t0 = asr[pairs[prev][0]]["end"]
                    t1 = asr[pairs[nxt][0]]["start"]
                    frac = (k - prev) / max(1, nxt - prev)
                    t = t0 + max(0.0, t1 - t0) * frac
                elif prev is not None:
                    t = asr[pairs[prev][0]]["end"] + step * (k - prev)
                elif nxt is not None:
                    t = asr[pairs[nxt][0]]["start"] - step * (nxt - k)
                else:
                    t = words[-1].end if words else 0.0
                words.append(LyricWord(raw, t, t + step, 0.35))
        out.append(LyricLine(line, words))
    return out


def to_cards(lines: list[LyricLine], accent_pick=None, max_words: int = 3) -> list[dict]:
    """Lyric lines -> phrase cards.

    Phrasing comes from the LINE, not from arithmetic. A line is chopped into
    groups of `max_words` and the group boundaries are pulled forward to the
    nearest sensible break (before a conjunction, never between "when I'm" and
    "not"). Time is then distributed inside the line in proportion to character
    count, anchored to the line's own first and last sung word — so a line the
    ASR only partly caught still reads at the right speed instead of stretching
    one word across six seconds.
    """
    BREAK_BEFORE = {"when", "and", "but", "who", "that", "it's", "so", "cause",
                    "cuz", "all", "i'm"}
    cards: list[dict] = []
    for line in lines:
        ws = line.words
        if not ws:
            continue
        span = max(0.35, ws[-1].end - ws[0].start)
        # group indices
        groups: list[list[int]] = []
        cur: list[int] = []
        for i, w in enumerate(ws):
            token = _norm(w.text)
            if cur and (len(cur) >= max_words
                        or (len(cur) >= 3 and token in BREAK_BEFORE)):
                groups.append(cur)
                cur = []
            cur.append(i)
        if cur:
            groups.append(cur)
        # a one-word fragment on its own is not a card; fold it into its
        # neighbour so we never show "around" alone for a second and a half
        if len(groups) > 1 and len(groups[-1]) == 1:
            groups[-2].extend(groups.pop())

        total_chars = sum(len(ws[i].text) + 1 for i in range(len(ws)))
        acc = 0
        for gi, g in enumerate(groups):
            chars = sum(len(ws[i].text) + 1 for i in g)
            t0 = ws[0].start + span * (acc / total_chars)
            acc += chars
            t1 = ws[0].start + span * (acc / total_chars)
            if gi == len(groups) - 1:
                t1 = ws[-1].end
            text = " ".join(ws[i].text for i in g)
            text = re.sub(r"[,?]+$", "", text).strip()
            cards.append({"start": round(t0, 3), "end": round(t1, 3),
                          "text": text,
                          "accent": accent_pick(text) if accent_pick else ""})
    return cards


ACCENT_WORDS = {"beauty", "beat", "complete", "yours", "life", "need", "make"}


def accent_for(text: str) -> str:
    """The one word per card that carries the line."""
    for w in re.split(r"[\s,]+", text):
        if _norm(w) in ACCENT_WORDS:
            return w
    return ""


def tighten(cards: list[dict], max_span: float = 3.2,
            min_span: float = 0.30) -> list[dict]:
    """Make the card list playable.

    Two things always need fixing after alignment: cards whose spans overlap
    (a phrase and its neighbour both claiming the same second) and cards stretched
    over an ASR gap, which sit still for six seconds and read as broken. Overlaps
    are clamped to the next card's start; long cards are split at word boundaries
    and the words re-spaced across the original span.
    """
    cards = sorted((dict(c) for c in cards if c.get("text", "").strip()),
                   key=lambda c: c["start"])

    # clamp overlap onto the next card's start
    for a, b in zip(cards, cards[1:]):
        if a["end"] > b["start"]:
            a["end"] = max(a["start"] + min_span, b["start"])

    # split anything that overstays
    out: list[dict] = []
    for c in cards:
        span = c["end"] - c["start"]
        words = c["text"].split()
        # to_cards already phrases within a line, so a long span here means the
        # SONG is slow there, not that the card is broken. Only split a card that
        # is both long and wordy; never re-chunk a phrase of two or three words.
        if span <= max_span or len(words) < 4:
            out.append(c)
            continue
        n = max(2, int(span / max_span) + 1)
        per = max(1, len(words) // n + (1 if len(words) % n else 0))
        chunks = [words[i:i + per] for i in range(0, len(words), per)]
        frac = len(chunks)
        for i, ch in enumerate(chunks):
            t0 = c["start"] + span * i / frac
            t1 = c["start"] + span * (i + 1) / frac
            out.append({"start": round(t0, 3), "end": round(t1, 3),
                        "text": " ".join(ch),
                        "accent": c.get("accent", "") if i == frac - 1 else ""})
    return out


def lyric_cards(track: str, start: float, duration: float,
                lines: list[str] | None = None) -> list[dict]:
    """The whole job: track -> timed lyric cards on the edit's clock."""
    if not lines:
        # There is deliberately no built-in lyric here. The words are an INPUT.
        # A guessed chorus once shipped cards the song never sings, on correct
        # timings, which is worse than no cards at all: it is confidently wrong.
        raise ValueError("no lyric text supplied — captions are an input, "
                         "never an inference")
    asr = transcribe(track, start, duration)
    aligned = align(lines, asr)
    return tighten(to_cards(aligned, accent_for))


def first_vocal(track: str, start: float, duration: float) -> float | None:
    """Seconds into the edit where the singing starts (None if instrumental)."""
    asr = transcribe(track, start, duration)
    return min((w["start"] for w in asr), default=None)
