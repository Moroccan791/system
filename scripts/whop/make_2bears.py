#!/usr/bin/env python3
"""Render the picked moments of 2 Bears Ep. 344 into shippable posts.

    .venv/bin/python scripts/whop/make_2bears.py --picks work/two_bears/picks.json
    .venv/bin/python scripts/whop/make_2bears.py --picks ... --only 3

One pick file in, one folder per post out:

    campaigns/two_bears_ep344/<slug>/<slug>.mp4     1080x1920, -16 LUFS
    campaigns/two_bears_ep344/<slug>/cover.jpg      the frame that reads in a grid
    campaigns/two_bears_ep344/<slug>/cards.json     what the renderer drew
    campaigns/two_bears_ep344/<slug>/POST.md        copy, hashtags, gate result

The pick file is the only editorial input, and it is written by the person who
watched the transcript, not by the renderer:

    [{"slug": "cold_plunge", "start": 755.0, "end": 792.0,
      "title": "...", "line": "...", "why": "..."}]

`start` is snapped back to the beginning of its sentence and `end` forward to
the end of the closing one, because a clip that starts mid-clause is the single
most common reason a comedy cut does not land. The snapped window is what gets
written back into the pick file, so the folder and the JSON never disagree.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import cv2                   # noqa: E402
import cover as COV          # noqa: E402
import qc_gate as QG         # noqa: E402
import render_clip as RC     # noqa: E402
import topic_guard as TG     # noqa: E402

CAMPAIGN = "two_bears_ep344"
TAGS = ["#2BearsWeekly", "#2Bears1Cave", "#TomSegura", "#BertKreischer",
        "#Comedy", "#PodcastClips", "#StandUpComedy", "#Funny"]


def load_words(path: Path) -> list[dict]:
    return json.loads(path.read_text())["words"]


def snap(words: list[dict], start: float, end: float, *, sentence_lead: float = 4.0) -> tuple[float, float]:
    """Grow [start, end] out to whole sentences.

    Backwards to the nearest sentence boundary within `sentence_lead` seconds,
    forwards to the first one after `end`. Bounded so a one-line pick cannot
    swallow half a minute of unrelated setup.
    """
    before = [w for w in words if float(w["end"]) <= start + 0.05]
    s = start
    for w in reversed(before):
        if start - float(w["start"]) > sentence_lead:
            break
        if str(w["text"]).rstrip('"\')').endswith((".", "?", "!")):
            s = float(w["end"])
            break

    after = [w for w in words if float(w["start"]) >= end - 0.05]
    e = end
    for w in after:
        if float(w["end"]) - end > 4.0:
            break
        if str(w["text"]).rstrip('"\')').endswith((".", "?", "!")):
            e = float(w["end"])
            break
    return round(s, 2), round(e, 2)


def post_md(pick: dict, info: dict, report: dict) -> str:
    fails = [r for r in report["checks"] if r["status"] == "fail"]
    rows = "\n".join(f"- `{r['status']}` **{r['name']}** — {r['detail']}"
                     for r in report["checks"])
    return f"""# {pick['title']}

**{pick['line']}**

## Why this moment

{pick['why']}

Window: {pick['start']:.1f}s → {pick['end']:.1f}s of the episode
({info['duration']:.1f}s cut, {info['cards']} caption cards).

## Copy — post as-is

> {pick['line']}
>
> 2 Bears 1 Cave Ep. 344 is out — full episode in my bio.
>
> {' '.join(TAGS)}

Required and non-negotiable: the words **2 Bears 1 Cave Ep. 344**, the tag
**#2BearsWeekly**, and https://youtu.be/3pDAyRLPO58 in the **bio**. Missing any
of the three means the post is not paid, however it performs.

## Gate

`{'PASS' if report['ok'] else 'FAIL'}` — {len(fails)} failure(s).

{rows}

## Files

- `{pick['slug']}.mp4` — 1080x1920, 29.97 fps, H.264 + AAC, -16 LUFS
- `cover.jpg` — {info.get('cover_at', '?')}s, chosen on sharpness/face/exposure
- `cards.json` — the captions that were drawn, with their times
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--picks", required=True)
    ap.add_argument("--transcript", default="work/two_bears/asr/episode.json")
    ap.add_argument("--source", default="work/two_bears/full.mp4")
    ap.add_argument("--only", type=int, help="render just this 1-based pick")
    ap.add_argument("--no-snap", action="store_true")
    args = ap.parse_args()

    picks_path = Path(args.picks)
    picks = json.loads(picks_path.read_text())
    words = load_words(Path(args.transcript))
    rules = json.loads((ROOT / "campaigns" / CAMPAIGN / "campaign_rules.json").read_text())
    rules.setdefault("_campaign", CAMPAIGN)
    lex = TG.load_lexicon(ROOT / "campaigns" / CAMPAIGN)

    dirty = False
    for i, pick in enumerate(picks, 1):
        if args.only and i != args.only:
            continue
        if not args.no_snap:
            s, e = snap(words, float(pick["start"]), float(pick["end"]))
            if (s, e) != (pick["start"], pick["end"]):
                pick["start"], pick["end"] = s, e
                dirty = True

        inside = [w for w in words if pick["start"] - 0.2 <= float(w["start"]) < pick["end"]]
        hits = TG.scan_words(inside, lexicon=lex)
        blocked = [h for h in hits if h["severity"] == "block"]
        if blocked:
            detail = ", ".join(f"{h['category']}:'{h['term']}'" for h in blocked[:4])
            print(f"[{i}] {pick['slug']}: REFUSED - {detail}")
            continue

        folder = ROOT / "campaigns" / CAMPAIGN / pick["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / f"{pick['slug']}.mp4"
        print(f"[{i}] {pick['slug']}  {pick['start']:.1f}-{pick['end']:.1f}s "
              f"({pick['end'] - pick['start']:.1f}s)", flush=True)
        info = RC.render(campaign=CAMPAIGN, start=pick["start"], end=pick["end"],
                         out=video, transcript=Path(args.transcript),
                         source=Path(args.source))

        best = COV.best_frame(video, start=0.6)
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(best["at"]) * 1000)
        ok, frame = cap.read()
        cap.release()
        if ok:
            cv2.imwrite(str(folder / "cover.jpg"),
                        cv2.resize(frame, (540, 960), interpolation=cv2.INTER_AREA),
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            info["cover_at"] = round(float(best["at"]), 2)

        manifest = json.loads(Path(info["manifest"]).read_text())
        manifest["title"] = pick.get("line")
        report = QG.gate(video, manifest, rules)
        (folder / "qc.json").write_text(json.dumps(report, indent=1) + "\n")
        (folder / "POST.md").write_text(post_md(pick, info, report))
        mark = "PASS" if report["ok"] else "FAIL"
        print(f"    {mark}  " + "; ".join(f"{r['name']}={r['status']}"
                                          for r in report["checks"]
                                          if r["status"] != "pass"), flush=True)

    if dirty:
        picks_path.write_text(json.dumps(picks, indent=1) + "\n")
        print(f"pick windows snapped and written back to {picks_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
