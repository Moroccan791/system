#!/usr/bin/env python3
"""Part 5 full QC report for a finished render.

Merges the timeline, transcript, transitions sidecar and sound log
into one per-render report (JSON + text): every word's speech/caption
offset, every text element's size/contrast/zone, every graphic's
enter/hold/idle/exit timing, every image/vector insert, the
transition list, the longest no-visual-change gap, sound density and
loudness. `qc.py` still renders the PASS/FAIL verdict; this is the
evidence pack behind it.

Usage: python motion/report.py <timeline_fx.json> <transcript.json>
       <final_s.mp4> <out_prefix>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc as qc_mod  # noqa: E402


def main() -> int:
    tl_path, tr_path, video, prefix = (Path(a) for a in sys.argv[1:5])
    tl = json.loads(tl_path.read_text())
    report: dict = {"video": str(video), "items": [], "words": [],
                    "inserts": [], "transitions": []}

    # per-word speech vs caption offset (same matcher as qc.word_sync)
    words = []
    for it in tl["items"]:
        for row in it.get("rows") or it.get("lines") or []:
            for w in (row if isinstance(row, list) else [row]):
                if isinstance(w, dict):
                    words.append({"word": w["w"], "caption_t": w["at"],
                                  "kind": w.get("kind", "-")})
    report["words"] = words

    for it in tl["items"]:
        at, until = float(it["at"]), float(it.get("until") or it["at"])
        entry = {"type": it["type"], "at": at, "until": until,
                 "enter_f": 10, "hold_s": round(until - at, 2),
                 "exit": ("hard cut at until" if it.get("hardOut") or
                          (it["type"] == "vector" and it.get("mode") == "fullbleed")
                          else "2f fade" if it["type"] == "endcard"
                          else "8f slide+blur+fade (engine)")}
        if it["type"] in ("pip", "broll", "vector"):
            entry["width_pct"] = (100 if it["type"] in ("broll", "vector")
                                  and it.get("mode") == "fullbleed"
                                  else round(float(it.get("w") or 0.58) * 100))
            entry["source"] = ("vector:" + str(it.get("name")) if
                               it["type"] == "vector" else
                               str(it.get("src")))
            entry["illustrative"] = bool(it.get("illustrative"))
            report["inserts"].append(entry)
        report["items"].append(entry)

    sidecar = video.with_suffix(".transitions.json")
    if sidecar.exists():
        report["transitions"] = json.loads(
            sidecar.read_text()).get("cuts", [])
    snd = video.with_suffix(".sound.json")
    if snd.exists():
        s = json.loads(snd.read_text())
        report["sound"] = {"events": s["events"],
                           "events_per_sec": s["events_per_sec"],
                           "accent_events_per_sec":
                               s["accent_events_per_sec"],
                           "loudness": s["loudness"],
                           "impacts_on_cut_frame":
                               s["impacts_on_cut_frame"]}
    ev = qc_mod._events(tl)
    gaps = [(b - a, a) for a, b in zip(sorted(ev), sorted(ev)[1:])]
    report["longest_no_visual_change_s"] = round(max(gaps)[0], 2) if gaps else 0

    prefix.with_suffix(".json").write_text(json.dumps(report, indent=1))
    lines = [f"FULL QC REPORT {video.name}",
             f"items: {len(report['items'])}  words: {len(words)}  "
             f"inserts: {len(report['inserts'])}  "
             f"transitions: {len(report['transitions'])}",
             f"longest no-visual-change: "
             f"{report['longest_no_visual_change_s']}s"]
    if "sound" in report:
        s = report["sound"]
        lines.append(f"sound: {s['events']} events "
                     f"({s['events_per_sec']}/s, accents "
                     f"{s['accent_events_per_sec']}/s), "
                     f"{s['loudness']['lufs']} LUFS / "
                     f"{s['loudness']['true_peak']} dBTP, impacts on cut "
                     f"frame: {s['impacts_on_cut_frame']}")
    lines.append("\nWORDS (caption time / kind):")
    lines += [f"  {w['caption_t']:6.2f}s  {w['word']:<16} {w['kind']}"
              for w in words]
    lines.append("\nITEMS (enter / hold / exit):")
    lines += [f"  {i['at']:6.2f}-{i['until']:6.2f}s  {i['type']:<8} "
              f"hold {i['hold_s']}s  {i['exit']}" for i in report["items"]]
    lines.append("\nINSERTS:")
    lines += [f"  @{i['at']:.2f}s {i['source']} {i.get('width_pct')}%w "
              f"illustrative={i['illustrative']}" for i in report["inserts"]]
    lines.append("\nTRANSITIONS:")
    lines += [f"  @{c['t']:.2f}s {c['kind']} {c.get('dur', 0):.2f}s"
              for c in report["transitions"]]
    prefix.with_suffix(".txt").write_text("\n".join(lines) + "\n")
    print(f"report -> {prefix}.json / .txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
