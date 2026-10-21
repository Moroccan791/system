#!/usr/bin/env python3
"""Turn one picked moment into a caption plan for build_whop_clip.

    .venv/bin/python scripts/whop/mkplan.py what_did_you_do --hero hated,nothing

This replaces the hand-written plan per post. It reads the picks (span,
emphasis), the episode's own word timings and the plan base (crops, splits),
then writes `plans/tb_<slug>.json`:

* every spoken word in the span becomes a caption cell, verbatim;
* words the picks call out are `key` - white captions, green emphasis, and
  visibly larger than the connective words, which is the house look;
* a card with none of them promotes its strongest content word, so the colour
  rhythm never drops to a wall of white for several cards;
* a `hero` word (the picks' strongest) gets its own 250 px row where the
  spoken order allows it: the renderer advances its clock line by line, so a
  hero may only move to a line edge, never reorder the sentence;
* the clip closes on the brand card, never on the peak.

Censoring is NOT done here: build_whop_clip masks 18+ words after it has
matched each line against the transcript, so the spoken token stays verbatim
for timing and only the glyphs change.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR                      # noqa: E402
from clipper.captions.block import censor_text   # noqa: E402

CAMPAIGN = "two_bears_ep344"
ZONE = "lower"           # lower third, clear of the platform's own caption band

#: words that carry no meaning on their own - never promoted to emphasis
STOP = set("""the and a i to of it in you that was is for on with as at but so my me
    he she they we do did not no or if just like what had have been be your his her
    this there then when about get got out up all one how im its dont didnt know
    yeah oh well""".split())


def content_score(cell: dict) -> int:
    """How much a word deserves the green: long, content-bearing, not a filler.

    Four letters is the floor ("fan", "video", "door" all carry a line); a
    pure-connector card ("it's you know, it's a not a") scores nothing and is
    left white on purpose - it reads as the breath between two colour beats.
    """
    b = CR.bare(cell["w"])
    if b in STOP or len(b) < 4:
        return -1
    return len(b)


def cells_for(words: list[dict], span: tuple[float, float],
              emphasis: list[str], drops: list[list[float]] | None = None) -> list[dict]:
    """Caption cells for the span, minus anything the cut deletes.

    A `drops` entry removes a stretch of source (a stammered repeat, a stumble
    the speaker made and then made again), and tight_base cuts it out - so the
    caption must not author the words that are no longer in the audio.
    """
    emph = {CR.bare(e) for e in emphasis}
    gone = [(float(a), float(b)) for a, b in (drops or [])]

    def dropped(t: float) -> bool:
        return any(a <= t < b for a, b in gone)

    return [{"w": w["text"], "at": w["start"], "end": w["end"],
             "kind": "key" if CR.bare(w["text"]) in emph else "conn"}
            for w in words if span[0] - 0.01 <= w["start"] <= span[1] + 0.01
            and not dropped(w["start"])]


def caption_beat(lines: list[list[dict]]) -> dict:
    return {"type": "caption", "zone": ZONE,
            "lines": [" ".join(c["w"] for c in l) for l in lines],
            "kinds": [[c["kind"] for c in l] for l in lines]}


def build(words, span, emphasis, hero_words, drops=None) -> list[dict]:
    """Cards for one span, with the picks' emphasis on the green words."""
    hero_set = {CR.bare(h) for h in hero_words}
    cards = CR.wrap_cells(cells_for(words, span, emphasis, drops))

    def next_at(ci: int, wi: int) -> float | None:
        """The next spoken word after (card, index) - the card's hard exit."""
        flat = [c for l in cards[ci]["lines"] for c in l]
        if wi + 1 < len(flat):
            return flat[wi + 1]["at"]
        for later in cards[ci + 1:]:
            return later["lines"][0][0]["at"]
        return None

    beats: list[dict] = []
    HERO_MIN = 0.45          # a 250 px hero row needs a beat, not a flash
    for ci, card in enumerate(cards):
        flat = [c for l in card["lines"] for c in l]
        if not any(c["kind"] == "key" for c in flat):
            best = max(flat, key=content_score)
            if content_score(best) >= 4:
                best["kind"] = "key"

        hero = next((c for c in flat
                     if CR.bare(c["w"]) in hero_set and c["kind"] == "key"), None)
        idx = flat.index(hero) if hero is not None else None
        if hero is not None and idx == 0 and next_at(ci, idx) is not None \
                and next_at(ci, idx) - hero["at"] >= HERO_MIN:
            hero["kind"] = "hero"          # hero leads; the rest re-wraps after it
            beats.append(caption_beat([[hero]]))
            beats += [caption_beat(c["lines"]) for c in CR.wrap_cells(flat[1:])]
            continue
        if hero is not None and idx == len(flat) - 1 \
                and (next_at(ci, idx) is None
                     or next_at(ci, idx) - hero["at"] >= HERO_MIN):
            hero["kind"] = "hero"          # hero lands; the rest re-wraps before it
            beats += [caption_beat(c["lines"]) for c in CR.wrap_cells(flat[:-1])]
            beats.append(caption_beat([[hero]]))
            continue
        beats.append(caption_beat([list(l) for l in card["lines"]]))
    return beats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--hero", default="", help="comma-separated hero words")
    ap.add_argument("--campaign", default=CAMPAIGN)
    ap.add_argument("--words", default="work/two_bears/asr/windows.json")
    ap.add_argument("--endcard", default="2 BEARS | 1 CAVE · EP. 344",
                    help="brand card title lines, ' | ' separated; '' to skip")
    ap.add_argument("--endcard-sub", default="FULL EPISODE IN BIO")
    args = ap.parse_args()

    picks = {p["slug"]: p for p
             in json.loads((ROOT / "campaigns" / args.campaign / "picks.json").read_text())}
    pick = picks[args.slug]
    words = json.loads((ROOT / args.words).read_text())["words"]
    base = ROOT / "scripts" / "whop" / "plans" / f"_{args.slug}_base.json"
    plan = json.loads(base.read_text())
    plan["post"] = args.slug                     # the style-card video key
    plan["beats"] = build(words, plan["span"], pick["emphasis"],
                          [h for h in args.hero.split(",") if h],
                          plan.get("drops"))
    plan["posting"]["title"] = censor_text(pick["title"])
    plan["posting"]["disclosure"] = ""           # the show's own channel: not an ad
    plan["posting"]["requiredLine"] = (
        "2 Bears 1 Cave Ep. 344 - full episode in the bio.")
    if args.endcard:
        plan["beats"].append({
            "type": "endcard", "after": "last", "gap": 0.30, "dur": 1.5,
            "title": args.endcard.split(" | ")[0],
            "titleLines": args.endcard.split(" | "),
            "sub": args.endcard_sub, "wordSize": 150})
    out = ROOT / "scripts" / "whop" / "plans" / f"tb_{args.slug}.json"
    out.write_text(json.dumps(plan, indent=1) + "\n")
    greens = sum(1 for b in plan["beats"] for k in b.get("kinds", []) for x in k
                 if x in ("key", "hero"))
    heroes = sum(1 for b in plan["beats"] for k in b.get("kinds", []) for x in k
                 if x == "hero")
    print(f"{out.name}: {len(plan['beats'])} cards, {greens} green words, "
          f"{heroes} hero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
