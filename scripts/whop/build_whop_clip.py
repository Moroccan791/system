#!/usr/bin/env python3
"""Build a whop clip (timeline + base spec) from a PLAN file.

    python scripts/whop/build_whop_clip.py plans/post2.json

The plan is data: which lines become captions, where a full-screen
graphic lands, which word triggers it, how the clip ends. The builder
resolves every word against the episode transcript (so captions land on
the real acoustic onset, never a hand-typed time), refuses to cut a
phrase in half, and writes:

    work/street/<post>/timeline.json   (the creative timeline)
    work/street/<post>/spec.json       (the base spec for tight_base.py)

Beat types
    caption   words -> one caption group (zone + size by the zone name)
    list      the full-screen diagram (the spoken words name the rows)
    vector    a full-screen vector scene (trophy/cup/network/...)
    endcard   the outro slate (always last, always with the fade)

Zones
    face      [0.55, 0.66]  over her (chest height, never the face)
    graphic   [0.30, 0.36]  over a full-screen graphic: a headline
    scene     [0.30, 0.36]  over a full-screen scene
    payoff    [0.73, 0.84]  low, over the two-shot (hands move at .47)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGNS = ROOT / "campaigns" / "street_you_grew_up_on"
EPISODE = ROOT / "work" / "street" / "asr" / "episode_transcript.json"

ZONES = {
    "face":   ([0.55, 0.66], 88),
    "graphic": ([0.30, 0.36], 118),
    "scene":  ([0.30, 0.36], 104),
    "payoff": ([0.73, 0.84], 92),
}
SIZES = {"sm": 88, "md": 104, "lg": 118}


def load_words(span, transcript_path=EPISODE, offset=0.0):
    """Words inside the window, in absolute source seconds.

    The transcript may be relative to its own window (clipper writes
    t=0 at the window start), so `offset` maps it to source time -
    the same convention tight_base.py uses.
    """
    data = json.loads(Path(transcript_path).read_text())
    words = [{"text": w["text"], "start": w["start"] + offset,
              "end": w["end"] + offset}
             for w in data["words"]
             if w["start"] + offset >= span[0] - 0.05
             and w["end"] + offset <= span[1] + 0.05]
    return words


class Clock:
    """Resolves spoken words to absolute source times, in order."""

    def __init__(self, words):
        self.words = words
        self.i = 0

    def find(self, text, advance=True, occurrence=1):
        """The occurrence-th time this word is spoken from the cursor."""
        hits = []
        for i in range(self.i, len(self.words)):
            w = self.words[i]
            if w["text"].lower().strip(".,!?") == text.lower().strip(".,!?"):
                hits.append((i, w))
                if len(hits) >= occurrence:
                    break
        if not hits:
            raise ValueError(f"word {text!r} not spoken after cursor "
                             f"({self.i})")
        i, w = hits[0]
        if advance:
            self.i = i + 1
        return round(w["start"], 2)

    def at(self, text):
        """A word already spoken - names a graphic, does not move the
        caption cursor."""
        for w in self.words:
            if w["text"].lower().strip(".,!?") == text.lower().strip(".,!?"):
                return round(w["start"], 2)
        raise ValueError(f"word {text!r} not spoken in this clip")


def build(plan: dict) -> dict:
    campaign = plan.get("campaign", "street_you_grew_up_on")
    post = plan["post"]
    style_file = CAMPAIGNS / post / "style.json"
    if not style_file.exists():
        style_file = CAMPAIGNS / "style.json"
    style = json.loads(style_file.read_text())
    accent = style["colors"]["accent"]
    span = plan["span"]
    transcript = plan.get("transcript", EPISODE)
    offset = float(plan.get("offset", 0.0))
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
    for beat in plan["beats"]:
        kind = beat["type"]
        if kind == "caption":
            zone_name = beat.get("zone", "face")
            zone, default_size = ZONES[zone_name]
            rows = []
            ats = []
            kinds = beat.get("kinds")
            for li, line in enumerate(beat["lines"]):
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
                raise ValueError("a caption line never exceeds four words")
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
                t = clock.at(trigger)
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
            t = clock.at(beat["trigger"])
            start = beat.get("at")
            if start is None:
                start = t - beat.get("lead", 0.07) + float(beat.get("offset", 0.0))
            end = beat.get("until")
            if end is None:
                end = start + beat.get("dur", 1.0)
            item = {"type": "vector", "name": beat["name"], "mode": "fullbleed",
                    "at": round(start, 2), "until": round(end, 2), "accent": accent}
            for k in ("offsetY", "radius", "title", "count", "label"):
                if k in beat:
                    item[k] = beat[k]
            items.append(item)
        elif kind == "endcard":
            at, until = beat.get("at"), beat.get("until")
            if at is None and beat.get("after") == "last":
                # the outro starts when the last caption has finished:
                # the speaker stops, the picture fades, the slate comes up
                last_caption = max((it for it in items if it["type"] == "poster"),
                                   key=lambda it: it["at"], default=None)
                base_at = (last_caption["_last"] if last_caption else 0.0)
                at = round(base_at + beat.get("gap", 0.18), 2)
                until = round(at + beat.get("dur", 1.1), 2)
            items.append({
                "type": "endcard", "at": at, "until": until,
                "title": beat.get("title", "STREET YOU GREW UP ON"),
                "titleLines": beat.get("titleLines"),
                "sub": beat.get("sub", "@street_you_grew_up_on"),
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
            it["until"] = round(min(max(last + 0.12, last + 0.95), nxt - 2 / 30), 3)
        else:
            it["until"] = round(last + 0.95, 3)
    # A caption is never cancelled by a graphic: MOTIONS.md rule 4 - the
    # caption layer runs UNDER everything, a full-screen scene is a
    # cutaway, not a caption break. The zone decides where it sits, so
    # the author puts a scene caption in the scene zone (top band) and
    # a face caption at chest height.
    duration = max(it.get("until", it["at"]) for it in items)
    # no negative times: the first word of a clip can land a hair
    # before zero once the silences are cut
    for it in items:
        it["at"] = max(0.0, round(float(it["at"]), 3))
        if it.get("until") is not None:
            it["until"] = round(max(it["at"] + 0.05, float(it["until"])), 3)
        for r in it.get("rows", []):
            for w in r:
                w["at"] = max(0.0, round(float(w["at"]), 3))

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
    out = ROOT / "work" / "street" / post
    out.mkdir(parents=True, exist_ok=True)
    (out / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")

    spec = {
        "source": plan.get("source", "work/street/raw/street_full.mp4"),
        "words": transcript,
        "offset": offset,
        "span": list(span),
        "drops": plan.get("drops", []),
        "crops": plan.get("crops", []),
        "out_base": str(out / "base.mp4"),
        "out_slice": str(out / "slice.json"),
        "tail_seconds": plan.get("tail_seconds", 1.35),
        "splits": plan.get("splits", []),
    }
    (out / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
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
        print("usage: build_whop_clip.py <plan.json>")
        return 2
    plan = json.loads(Path(sys.argv[1]).read_text())
    build(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
