#!/usr/bin/env python3
"""Posting-pack generator: hook variants, titles, covers.

One clip should ship with CHOICES: three hook framings (the
as-authored promise, a number-led variant, a curiosity variant),
three titles, a description, hashtags, and three cover frames
pulled from moments the timeline already makes strong (the hook
slate, the hero poster's midpoint, a late face frame). A human
picks; nothing here posts anything.

Usage:
  python motion/packaging.py <timeline.json> <transcript.json> \
      <out_dir> [<final.mp4>]
Writes <out_dir>/packaging.json (+ cover_*.jpg when a video is
given) and prints a one-line summary.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipper.ffmpeg import ffmpeg_exe  # noqa: E402

TOPICS = {
    ("men", "women", "dating", "relationship", "married", "wife",
     "husband", "girl", "guy"): ["#dating", "#relationships"],
    ("money", "rich", "business", "million", "sales", "income"):
        ["#money", "#business"],
    ("mindset", "discipline", "focus", "habit", "success"):
        ["#mindset", "#selfimprovement"],
    ("gym", "muscle", "workout", "fitness", "weight"):
        ["#fitness", "#gym"],
}


def words_of(tr) -> list[dict]:
    if isinstance(tr, dict):
        tr = tr.get("words") or []
    return [{"text": str(w.get("text") or w.get("word") or ""),
             "start": float(w["start"]),
             "end": float(w.get("end") or w["start"] + 0.3)}
            for w in tr if str(w.get("text") or w.get("word") or "").strip()]


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip(" .")


def build(tl: dict, tr, video: Path | None, out: Path) -> dict:
    words = words_of(tr)
    toks = [w["text"] for w in words]
    dur = float(tl.get("duration") or (words[-1]["end"] if words else 0))
    hook = next((i for i in tl["items"] if i["type"] == "hook"), None)
    authored = " ".join(hook["hookLines"]) if hook else \
        " ".join(toks[:6]).upper()
    num_i = next((i for i, t in enumerate(toks)
                  if re.fullmatch(r"\d[\d,\.]*%?", t.strip(".,!?"))), None)
    number_led = " ".join(toks[num_i:num_i + 4]).upper() \
        if num_i is not None else authored
    curiosity = clean(" ".join(toks[:8]))
    curiosity = (curiosity[:1].upper() + curiosity[1:]) + "…"
    variants = [
        {"strategy": "as-authored promise", "hook": authored},
        {"strategy": "number-led", "hook": number_led},
        {"strategy": "curiosity gap", "hook": curiosity},
    ]
    titles = [authored.title(), number_led.title(),
              f"Watch What Happens: {curiosity}"]
    utter = clean(" ".join(toks))
    description = (utter[:180].rsplit(" ", 1)[0] + "…"
                   if len(utter) > 180 else utter) + \
        "\n\nFollow for more."
    low = {re.sub(r"[^a-z]", "", t.lower()) for t in toks}
    tags = ["#shorts"]
    for keys, hs in TOPICS.items():
        if low & set(keys):
            tags += hs
    tags += ["#viral", "#fyp"]
    authored = tl.get("posting") or {}
    if authored:
        # The editor, not a keyword matcher, is responsible for campaign
        # restrictions. A single spoken "husband" must never turn a
        # Demi Lovato interview into #dating content. Preserve the
        # required description line byte-for-byte, including #ad.
        tags = list(authored["hashtags"])
        if not 7 <= len(set(tags)) <= 8 or len(set(tags)) != len(tags):
            raise ValueError("authored pack needs 7-8 unique hashtags")
        titles = [authored["title"]] + list(authored.get("alternativeTitles") or [])
        variants = list(authored.get("hookVariants") or variants)
        # Not every campaign is a paid read: an empty disclosure is a real
        # value (2 Bears 1 Cave is the show's own channel), and the pack then
        # carries no #ad line rather than a fake one.
        disclosure = authored["disclosure"].strip()
        description = (((disclosure + "\n") if disclosure else "") +
                       authored["description"].strip() + "\n\n" +
                       authored["requiredLine"])
        if authored["requiredLine"] not in description:
            raise ValueError("the campaign's required description line is missing")
        if disclosure and not description.startswith(("#ad\n", "#sponsored\n")):
            raise ValueError("campaign description line and ad disclosure are required")
    else:
        tags = list(dict.fromkeys(tags))[:8]
    pack = {"hook_variants": variants, "titles": titles,
            "description": description,
            "hashtags": tags,
            "covers": []}
    out.mkdir(parents=True, exist_ok=True)
    if video is not None and video.exists():
        hero = next((i for i in tl["items"] if i["type"] == "poster"
                     and any(w.get("kind") == "hero"
                             for r in i.get("rows") or [] for w in r)),
                    None)
        custom = authored.get("coverMoments")
        moments = list(zip(("cover_a_hook.jpg", "cover_b_hero.jpg", "cover_c_late.jpg"),
                           custom)) if custom else [
            ("cover_a_hook.jpg", 0.6),
            ("cover_b_hero.jpg",
             (float(hero["at"]) + float(hero["until"])) / 2
             if hero else dur * 0.3),
            ("cover_c_late.jpg", dur * 0.62)]
        for name, t in moments:
            dest = out / name
            r = subprocess.run(
                [ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{t:.2f}",
                 "-i", str(video), "-frames:v", "1", "-q:v", "3",
                 str(dest)], capture_output=True, text=True)
            if r.returncode == 0 and dest.exists():
                pack["covers"].append({"file": name, "at_s": round(t, 2)})
    out.mkdir(parents=True, exist_ok=True)
    (out / "packaging.json").write_text(json.dumps(pack, indent=1))
    return pack


def main() -> int:
    tl = json.loads(Path(sys.argv[1]).read_text())
    tr = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])
    video = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    pack = build(tl, tr, video, out)
    print(f"packaging: {len(pack['hook_variants'])} hook variants, "
          f"{len(pack['covers'])} covers, "
          f"{len(pack['hashtags'])} hashtags -> {out / 'packaging.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
