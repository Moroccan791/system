#!/usr/bin/env python3
"""Turn a rendered job's own files into the manifest the gate reads.

    .venv/bin/python scripts/whop/manifest_from_timeline.py work/street/post9

The campaign gate (scripts/whop/qc_gate.py) needs three things a finished
render already knows: the caption cards as they were set, the spoken words on
the cut's clock, and where the end card starts. Rather than making the gate
re-derive any of that (and risk disagreeing with what is on screen), this
reads them from the pipeline's own output:

* `timeline.json` - the posters, i.e. the captions that were actually built,
  plus the end card and the duration;
* `slice.json`   - the kept words with their times on the cut's clock.

Run by `make_post.py` between QC and delivery, so every new render is gated
without anyone having to remember. Also usable standalone on an old job.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTION_BAND = [1480, 1805]          # burned-in caption band, same as font_refresh


def measure(path: Path) -> float:
    """Duration straight from the file, used when the timeline has none."""
    import subprocess

    ff = subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()
    out = subprocess.run([ff, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return 0.0


def build(work: Path) -> dict:
    timeline = json.loads((work / "timeline.json").read_text())
    slice_path = work / "slice.json"
    words: list[dict] = []
    if slice_path.exists():
        for w in json.loads(slice_path.read_text()).get("words", []):
            words.append({"w": w.get("text", ""),
                          "at": round(float(w.get("start") or 0), 3),
                          "end": round(float(w.get("end") or 0), 3)})

    cards: list[dict] = []
    endcard: float | None = None
    # The band the captions actually occupy, from the timeline's own zones.
    # CAPTION_BAND is where burned-in subtitles used to sit; a render that
    # places its captions higher earns a band that matches, so the face check
    # judges the text that is on screen rather than a fixed strip.
    band = list(CAPTION_BAND)
    zones = [item.get("zone") for item in timeline.get("items", [])
             if item.get("type") == "poster" and item.get("zone")]
    if zones:
        band = [int(round(min(z[0] for z in zones) * 1920)),
                int(round(max(z[1] for z in zones) * 1920))]
    for item in timeline.get("items", []):
        kind = item.get("type")
        if kind in ("poster", "caption"):
            rows = item.get("rows") or []
            lines = [[str(cell.get("w", "")) for cell in row] for row in rows]
            if not any(lines):
                continue
            cards.append({"show_from": round(float(item.get("at") or 0), 3),
                          "show_until": round(float(item.get("until") or 0), 3),
                          "lines": lines})
        elif kind == "endcard" and endcard is None:
            endcard = round(float(item.get("at") or 0), 3)

    return {
        "campaign": timeline.get("campaign") or "",
        "post": work.name,
        "duration": float(timeline.get("duration") or 0.0),
        "endcard": endcard,
        "caption_band": band,
        "cards": sorted(cards, key=lambda c: c["show_from"]),
        "words_kept": sorted(words, key=lambda w: w["at"]),
        "source": "timeline.json + slice.json",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work", help="the job folder holding timeline.json")
    ap.add_argument("--video", help="also fix up duration from this file")
    ap.add_argument("--out", help="default: <work>/gate_manifest.json")
    args = ap.parse_args()

    work = Path(args.work)
    manifest = build(work)
    if args.video:
        real = measure(Path(args.video))
        if real:
            manifest["duration"] = round(real, 3)
    out = Path(args.out) if args.out else work / "gate_manifest.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{out}: {len(manifest['cards'])} cards, "
          f"{len(manifest['words_kept'])} words, "
          f"endcard {manifest['endcard']}, {manifest['duration']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
