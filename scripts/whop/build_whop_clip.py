#!/usr/bin/env python3
"""Build a whop clip (timeline + base spec) from a PLAN file.

    python scripts/whop/build_whop_clip.py plans/post2.json
    python scripts/whop/build_whop_clip.py plans/post2.json --check

The plan is data: which lines become captions, where a full-screen
graphic lands, which word triggers it, how the clip ends. The builder
resolves every word against the episode transcript (so captions land on
the real acoustic onset, never a hand-typed time), refuses to cut a
phrase in half, keeps every caption clear of her face, and writes:

    work/street/<post>/timeline.json   (the creative timeline)
    work/street/<post>/spec.json       (the base spec for tight_base.py)

Beat types
    caption   words -> one caption group (zone + size by the zone name)
    list      the full-screen diagram (the spoken words name the rows)
    vector    a full-screen vector scene (trophy/cup/network/...)
    endcard   the outro slate (always last, always with the fade)

Zones
    face      under her chin, measured on the actual base (never on
              her face - that is the thing v5 got rejected for)
    graphic   over a full-screen graphic: a headline
    scene     over a full-screen scene
    payoff    lower still, for the two-shot
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGNS = ROOT / "campaigns" / "street_you_grew_up_on"
EPISODE = ROOT / "work" / "street" / "asr" / "episode_transcript.json"

ZONES = {
    "face":   ([0.55, 0.66], 88),   # default; recomputed from the face report
    "graphic": ([0.30, 0.36], 118),
    "scene":  ([0.30, 0.36], 104),
    "payoff": ([0.73, 0.84], 92),
    "low":    ([0.82, 0.90], 92),   # close-up-safe lower third, clear of a low chin
}
SIZES = {"sm": 88, "md": 104, "lg": 118}
LOOKAHEAD = 1.0        # a caption word is never matched more than a second ahead
FIRST_LOOKAHEAD = 2.5  # the first word of a caption group may sit a beat later
DEFAULT_ENDCARD_GAP = 0.45   # short handoff; no long frozen-speaker hold
DEFAULT_ENDCARD_DURATION = 1.5  # leaves ~1s readable before a 0.5s fade
DEFAULT_LAST_CAPTION_TAIL = 0.35


def _norm(tok: str) -> str:
    return tok.lower().strip(".,!?\u2019\u201d'\"")


def face_zone(base: Path):
    """The caption band BELOW her face, measured on the actual base.

    A caption that lands on the face is the thing the user rejected in
    v5, so the band is derived from where the face actually ends: the
    caption sits under the chin, never across it.
    """
    report = base.parent / "face_report.json"
    if not report.exists():
        try:
            out = subprocess.run([str(ROOT / ".venv/bin/python"),
                                  str(ROOT / "motion" / "reframe.py"),
                                  "--report", str(base)],
                                 capture_output=True, text=True, cwd=ROOT)
            report.write_text(out.stdout)
        except Exception:
            return None
    try:
        d = json.loads(report.read_text())
    except Exception:
        return None
    bottom = float(d.get("face_bottom", 0.44))
    bmax = float(d.get("face_bottom_max", bottom))
    # the band clears the LOWEST chin in the clip, not the median one
    centre = min(max(max(bottom, bmax) + 0.10, 0.50), 0.72)
    return [round(centre - 0.055, 3), round(centre + 0.055, 3)]


def base_seconds(base: Path):
    """The length of the cut base, so the timeline can match it."""
    if not base.exists():
        return None
    try:
        out = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-c",
             "import imageio_ffmpeg,subprocess,sys;"
             "ff=imageio_ffmpeg.get_ffmpeg_exe();"
             "print(subprocess.run([ff,'-i',sys.argv[1]],capture_output=True,"
             "text=True).stderr)", str(base)],
            capture_output=True, text=True, cwd=ROOT)
        for line in out.stdout.splitlines():
            if "Duration:" in line:
                h, m, sec = (line.split("Duration:")[1].split(",")[0]
                             .strip().split(":"))
                return int(h) * 3600 + int(m) * 60 + float(sec)
    except Exception:
        pass
    return None


def load_words(span, transcript_path=EPISODE, offset=0.0):
    """Words inside the window, in absolute source seconds.

    The transcript may be relative to its own window (clipper writes
    t=0 at the window start), so `offset` maps it to source time -
    the same convention tight_base.py uses.
    """
    data = json.loads(Path(transcript_path).read_text())
    return [{"text": w["text"], "start": w["start"] + offset,
             "end": w["end"] + offset}
            for w in data["words"]
            if w["start"] + offset >= span[0] - 0.05
            and w["end"] + offset <= span[1] + 0.05]


class Clock:
    """Resolves spoken words to times, in order."""

    def __init__(self, words):
        self.words = words
        self.i = 0

    def _match(self, tok, anchor, limit):
        """The word this caption token lands on.

        Case matters where the ASR is consistent ("And" vs "and"), so
        an exact-case hit wins; otherwise the first case-insensitive
        hit inside the window does.
        """
        key = _norm(tok)
        first = None
        compound = None
        j = self.i
        while j < len(self.words) and self.words[j]["start"] - anchor <= limit:
            current = _norm(self.words[j]["text"])
            if current == key:
                if self.words[j]["text"] == tok:
                    return j
                if first is None:
                    first = j
            # Whisper occasionally splits the ordinary spoken word
            # "into" into adjacent "in" + "to" tokens. Match that as one
            # caption word at the true onset, without falsely fusing it
            # to the preceding word.
            if key == "into" and current == "in" and j + 1 < len(self.words) \
                    and _norm(self.words[j + 1]["text"]) == "to" \
                    and self.words[j + 1]["start"] - anchor <= limit \
                    and compound is None:
                compound = j
            j += 1
        return first if first is not None else compound

    def line(self, text):
        """A caption LINE written as prose.

        The words are matched against the transcript from the cursor, so
        the caption lands on the syllable that was actually spoken - and
        the plan can be written as the sentence the speaker said.
        """
        row = []
        anchor = (self.words[self.i]["start"] if self.i < len(self.words)
                  else 0.0)
        for n, tok in enumerate(text.split()):
            key = _norm(tok)
            # the first word of a caption group may sit a beat after the
            # previous group; every word after it must follow closely
            limit = FIRST_LOOKAHEAD if n == 0 else LOOKAHEAD
            j = self._match(tok, anchor, limit)
            if j is None:
                j = len(self.words)      # too far ahead: treat as unheard
            if j >= len(self.words):
                # The ASR sometimes drops a short word ("next to it" ->
                # "next to?"). The caption still has to be right, so the
                # missing word is FUSED onto the previous one and the
                # line is flagged for review.
                if row:
                    prev = row[-1]
                    print(f"  ! fused (not heard): {tok!r} in {text!r}")
                    row.append({"w": tok, "at": round(prev["at"] + 0.08, 2),
                                "kind": "conn"})
                    continue
                raise ValueError(f"line {text!r}: {tok!r} is not spoken after "
                                 f"cursor {self.i}")
            w = self.words[j]
            compound = (key == "into" and _norm(w["text"]) == "in"
                        and j + 1 < len(self.words)
                        and _norm(self.words[j + 1]["text"]) == "to")
            # The plan supplies the verbatim caption token (punctuation
            # included); ASR casing/punctuation is only a timing hint.
            row.append({"w": tok, "at": round(w["start"], 2), "kind": "conn"})
            self.i = j + 2 if compound else j + 1
            # Anchor the next token at this word's END, not its onset. A
            # stretched word such as "negative" can last >1s while the
            # next spoken word is still contiguous and must not be fused.
            anchor = self.words[j + 1]["end"] if compound else w["end"]
        return row

    def occurrences(self, text):
        """Every place in the clip where the phrase is spoken."""
        toks = text.split()
        if not toks:
            return []
        keys = [_norm(t) for t in toks]
        out = []
        for i in range(len(self.words) - len(keys) + 1):
            if all(_norm(self.words[i + k]["text"]) == keys[k]
                   for k in range(len(keys))):
                out.append(i)
        return out

    def _nearest(self, text):
        hits = self.occurrences(text)
        if not hits:
            return None
        # the occurrence closest to the caption cursor: a trigger that
        # names a line the captions already consumed still lands on it
        return min(hits, key=lambda i: abs(i - self.i))

    def phrase_at(self, text):
        """The time of the first word of a phrase - a graphic trigger.
        Does not move the caption cursor."""
        i = self._nearest(text)
        if i is None:
            raise ValueError(f"trigger {text!r} is not spoken in this clip")
        return round(self.words[i]["start"], 2)

    def at(self, text):
        """A word already spoken - names a graphic, does not move the
        caption cursor."""
        i = self._nearest(text)
        if i is None:
            raise ValueError(f"word {text!r} not spoken in this clip")
        return round(self.words[i]["start"], 2)


def phrase_reveal(row: list[dict], group_at: float | None = None):
    """Show a verbatim caption phrase at its first word while retaining
    original word times for sync, hold, and exit. Optional group_at lets
    multiple caption rows arrive together as one hook."""
    word_times = [float(w["at"]) for w in row]
    if not word_times:
        return [], group_at
    onset = min(word_times) if group_at is None else float(group_at)
    for word in row:
        word["showAt"] = onset
    return word_times, onset


def build(plan: dict) -> dict:
    campaign = plan.get("campaign", "street_you_grew_up_on")
    post = plan["post"]
    sys.path.insert(0, str(ROOT))
    from scripts.whop.style_card import is_style_approved
    if not is_style_approved(campaign, post):
        raise RuntimeError(f"style-card approval required for {campaign}/{post} before editing")
    style_file = ROOT / "campaigns" / campaign / post / "style.json"
    theme_file = ROOT / "motion" / "themes" / f"{campaign}__{post}.json"
    style = json.loads(style_file.read_text())
    theme = json.loads(theme_file.read_text())
    card = theme.get("styleCard") or {}
    if not (card.get("approved") is True and card.get("campaign") == campaign
            and card.get("video") == post and card.get("style_sha256")
            and is_style_approved(campaign, post, card.get("style_sha256"))):
        raise RuntimeError(f"approved style theme/receipt mismatch for {campaign}/{post}")
    accent = style["colors"]["accent"]
    span = plan["span"]
    transcript = plan.get("transcript", EPISODE)
    offset = float(plan.get("offset", 0.0))

    out = ROOT / "work" / "street" / post
    out.mkdir(parents=True, exist_ok=True)

    # the SPEC comes first: the cut can be built even when a caption
    # line cannot be matched yet (the words behind a drop are only
    # reachable on the cut's own clock)
    spec = {
        "source": plan.get("source", "work/street/raw/street_full.mp4"),
        "words": transcript,
        "offset": offset,
        "span": list(span),
        "drops": plan.get("drops", []),
        "crops": plan.get("crops", []),
        "out_base": str(out / "base.mp4"),
        "out_slice": str(out / "slice.json"),
        # A short tail gives the end card and final fade time to land.
        # The handoff gap/caption hold are bounded below; this is not a
        # reason to leave a visible speaker freeze on screen.
        "tail_seconds": plan.get("tail_seconds") or 1.7,
        "splits": plan.get("splits", []),
        **({"max_gap": float(plan["max_gap"])} if "max_gap" in plan else {}),
        **({"keep_gap": float(plan["keep_gap"])} if "keep_gap" in plan else {}),
    }
    (out / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")

    base_file = ROOT / "work" / "street" / post / "base.mp4"
    auto_face = face_zone(base_file) if base_file.exists() else None
    if auto_face:
        ZONES["face"] = (auto_face, ZONES["face"][1])
        ZONES["payoff"] = ([round(auto_face[0] + 0.18, 3),
                            round(auto_face[1] + 0.18, 3)], ZONES["payoff"][1])
    base_duration = base_seconds(base_file)

    # Word times must be CLIP-relative (the base's own clock, after the
    # silences were cut) - a caption that lands on the right syllable
    # in the source lands on the right syllable in the cut. So the
    # slice built by tight_base.py is the reference, not the source
    # transcript.
    slice_file = ROOT / "work" / "street" / post / "slice.json"
    if slice_file.exists():
        words = json.loads(slice_file.read_text())["words"]
    else:
        words = load_words(span, transcript, offset)
    clock = Clock(words)

    items = []
    last_caption_tail = DEFAULT_LAST_CAPTION_TAIL
    for beat in plan["beats"]:
        kind = beat["type"]
        if kind == "caption":
            zone_name = beat.get("zone", "face")
            zone, default_size = ZONES[zone_name]
            rows = []
            ats = []
            kinds = beat.get("kinds")
            reveal_group_at = None
            for li, line in enumerate(beat["lines"]):
                if isinstance(line, str):
                    row = clock.line(line)
                    word_times = [w["at"] for w in row]
                    if beat.get("reveal") == "phrase" and row:
                        # A hook may appear as a complete, verbatim phrase on
                        # its first spoken onset instead of trickling in one
                        # isolated word at a time. Keep original word times for
                        # the caption's exit/hold calculation.
                        word_times, reveal_group_at = phrase_reveal(
                            row, reveal_group_at)
                    ats.extend(word_times)
                    for wi, w in enumerate(row):
                        w["kind"] = beat.get("wordKind", "conn")
                        if kinds and li < len(kinds) and wi < len(kinds[li]):
                            w["kind"] = kinds[li][wi]
                    rows.append(row)
                    continue
                row = []
                for wi, w in enumerate(line):
                    t = clock.find(w)
                    kind = beat.get("wordKind", "conn")
                    if kinds and li < len(kinds) and wi < len(kinds[li]):
                        kind = kinds[li][wi]
                    row.append({"w": w, "at": t, "kind": kind})
                    ats.append(t)
                rows.append(row)
            if len(rows) > 2:
                raise ValueError("captions never exceed two lines")
            if any(len(r) > 4 for r in rows):
                bad = [r for r in rows if len(r) > 4]
                raise ValueError("a caption line never exceeds four words: "
                                 + " / ".join(" ".join(w["w"] for w in r)
                                              for r in bad))
            size = SIZES.get(beat.get("size", ""), default_size)
            items.append({
                "type": "poster", "at": min(ats), "rows": rows, "zone": zone,
                "captionStyle": style["captionStyle"], "connSize": size,
                "heroSize": beat.get("heroSize", 250), "hardOut": True,
                "_last": max(ats),
            })
        elif kind == "list":
            rows = []
            ats = []
            for label, trigger in beat["items"]:
                t = (clock.phrase_at(trigger) if " " in trigger
                     else clock.at(trigger))
                rows.append({"text": label, "at": t})
                ats.append(t)
            start = beat.get("at")
            if start is None:
                start = min(ats) - beat.get("lead", 0.07)
            end = beat.get("until")
            if end is None:
                end = max(ats) + beat.get("hold", 0.9)
            items.append({
                "type": "list", "layout": beat.get("layout", "diagram"),
                "at": round(start, 2), "until": round(end, 2),
                "hardOut": True, "accent": accent, "items": rows,
            })
        elif kind == "vector":
            t = (clock.phrase_at(beat["trigger"]) if " " in beat["trigger"]
                 else clock.at(beat["trigger"]))
            start = beat.get("at")
            if start is None:
                start = t - beat.get("lead", 0.07) + float(beat.get("offset", 0.0))
            end = beat.get("until")
            if end is None:
                end = start + beat.get("dur", 1.0)
            item = {"type": "vector", "name": beat["name"], "mode": "fullbleed",
                    "at": round(start, 2), "until": round(end, 2), "accent": accent}
            # every scene-specific key passes straight through
            # (word, quoteLines, entries, value, by, ...)
            for k, v in beat.items():
                if k in ("type", "name", "trigger", "at", "until", "dur",
                         "lead", "offset", "zone"):
                    continue
                item[k] = v
            items.append(item)
        elif kind == "endcard":
            at, until = beat.get("at"), beat.get("until")
            if at is None and beat.get("after") == "last":
                # the outro starts when the last caption has finished:
                # the speaker stops, the picture fades, the slate comes up
                last_caption = max((it for it in items if it["type"] == "poster"),
                                   key=lambda it: it["at"], default=None)
                base_at = (last_caption["_last"] if last_caption else 0.0)
                endcard_gap = float(beat.get("gap", DEFAULT_ENDCARD_GAP))
                last_caption_tail = max(0.12, endcard_gap - 0.10)
                at = round(base_at + endcard_gap, 2)
                until = round(at + beat.get("dur", DEFAULT_ENDCARD_DURATION), 2)
                if base_duration:
                    # The slate runs to the final frame. It may not wait
                    # on a held speaker frame after the closing line.
                    until = round(base_duration, 2)
                    at = round(until - beat.get("dur", DEFAULT_ENDCARD_DURATION), 2)
                    at = round(max(at, base_at + endcard_gap), 2)
            items.append({
                "type": "endcard", "at": at, "until": until,
                "title": beat.get("title", "STREET YOU GREW UP ON"),
                "titleLines": beat.get("titleLines"),
                "sub": beat.get("sub", ""),
                "wordSize": beat.get("wordSize", 148), "accent": accent,
            })
        else:
            raise ValueError(f"unknown beat type {kind!r}")

    # ---- each caption group ends where the next one starts ---------------
    posts = [it for it in items if it["type"] == "poster"]
    for i, it in enumerate(posts):
        last = it.pop("_last")
        if i + 1 < len(posts):
            nxt = posts[i + 1]["at"]
            # the exit never lands inside the last word: the word needs
            # its entry plus a beat (validator: 0.12s on a hard out)
            it["until"] = round(max(last + 0.12,
                                    min(last + 0.95, nxt - 2 / 30)), 3)
        else:
            it["until"] = round(last + last_caption_tail, 3)

    # no negative times: the first word of a clip can land a hair
    # before zero once the silences are cut
    for it in items:
        it["at"] = max(0.0, round(float(it["at"]), 3))
        if it.get("until") is not None:
            it["until"] = round(max(it["at"] + 0.05, float(it["until"])), 3)
        for r in it.get("rows", []):
            for w in r:
                w["at"] = max(0.0, round(float(w["at"]), 3))
                if w.get("showAt") is not None:
                    w["showAt"] = max(0.0, round(float(w["showAt"]), 3))

    duration = base_duration or max(it.get("until", it["at"]) for it in items)
    last_word_time = max((w["at"] for it in items
                          for r in it.get("rows", []) for w in r),
                         default=0.0)

    (out / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")

    timeline = {
        "version": 1, "width": 1080, "height": 1920, "fps": 30,
        "duration": round(duration, 2),
        "fadeOut": plan.get("fadeOut", 0.5),
        "brand": {"accent": accent},
        "posting": plan.get("posting", {}),
        "theme": {
            "radius": style.get("radius", "sharp"), "glow": 0, "speed": 1.0,
            "easing": "pop", "fontMode": "sans",
            "captionStyle": style["captionStyle"],
            "fontPack": style["caption"],
            "fonts": {k: style[k] for k in
                      ("caption", "keyword", "serif", "list", "endcard")},
            "colors": style["colors"],
        },
        "items": sorted(items, key=lambda x: x["at"]),
    }
    (out / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")

    print(f"{post}: {len(timeline['items'])} items, {timeline['duration']}s, "
          f"accent {accent}, style {style['captionStyle']}")
    for it in timeline["items"]:
        txt = "/".join(" ".join(w["w"] for w in r) for r in it.get("rows", []))
        if it["type"] == "list":
            txt = "/".join(x["text"] for x in it["items"])
        print(f'  {it["type"]:<8} {it["at"]:5.2f}-{it.get("until", 0):5.2f}  {txt}')
    return timeline


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: build_whop_clip.py <plan.json> [--check]")
        return 2
    plan = json.loads(Path(sys.argv[1]).read_text())
    if "--check" in sys.argv:
        bad = []
        for b in plan.get("beats", []):
            for line in b.get("lines", []):
                if isinstance(line, str) and len(line.split()) > 4:
                    bad.append(f'{len(line.split())}w  "{line}"')
        if bad:
            print("lines over four words:")
            for x in bad:
                print("   ", x)
            return 1
        print("plan ok: every caption line is four words or fewer")
        return 0
    try:
        build(plan)
    except ValueError as exc:
        # A caption after an authored drop may not be reachable on the
        # source clock. The spec is written before caption matching, so
        # let tight_base apply the drops; the second builder pass then
        # resolves every word on the exact cut clock. A failure after
        # slice.json exists is real and must stay loud.
        work = ROOT / "work" / "street" / plan["post"]
        if (work / "spec.json").exists() and not (work / "slice.json").exists():
            print(f"caption timing deferred until after the cut: {exc}")
            return 0
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
