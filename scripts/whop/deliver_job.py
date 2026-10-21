#!/usr/bin/env python3
"""Deliver a finished motion job into its campaign folder.

    .venv/bin/python scripts/whop/deliver_job.py \\
        --work work/street/what_did_you_do --campaign two_bears_ep344 \\
        --slug what_did_you_do

The render pipeline stops at `job/final_s.mp4`. Delivery is the part that used
to be hand-typed per post - copy the master, choose the cover so the grid
thumbnail is never a screenshot of subtitles, run the campaign gate against the
manifest the render itself implies, and write the post copy - so it lives here
instead, once, for every campaign.

Writes: <campaign>/<slug>/<slug>.mp4, cover.jpg, qc.json, POST.md.
Exit code is 0 only when the gate passes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "whop"))
import cover as COV          # noqa: E402


def caption_gaps(timeline: dict) -> list[tuple[float, float]]:
    """Stretches of the clip with no caption on screen at all.

    Pairing sorted edges is not enough - captions overlap their neighbours'
    start - so the covered time is unioned first, then inverted.
    """
    covered: list[tuple[float, float]] = []
    for item in timeline.get("items", []):
        if item.get("type") in ("poster", "card", "endcard"):
            covered.append((float(item["at"]), float(item.get("until") or item["at"])))
    covered.sort()
    merged: list[tuple[float, float]] = []
    for a, b in covered:
        if merged and a <= merged[-1][1] + 0.02:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    gaps, prev = [], 0.0
    for a, b in merged:
        if a - prev > 0.25:
            gaps.append((prev, a))
        prev = max(prev, b)
    dur = float(timeline.get("duration") or 0.0)
    if dur - prev > 0.25:
        gaps.append((prev, dur))
    return sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)


def write_post(folder: Path, timeline: dict, slug: str, qc: dict, dur: float) -> None:
    posting = timeline.get("posting") or {}
    tags = " ".join(posting.get("hashtags") or [])
    body = [
        f"# {posting.get('title', slug)}",
        "",
        f"`{slug}.mp4` - 1080x1920, {dur:.1f}s, white captions, green emphasis.",
        "",
        "## Caption to post",
        "",
        "```",
        posting.get("title", ""),
        "",
        str(posting.get("description", "")).strip(),
        "",
        str(posting.get("requiredLine", "")),
        "",
        tags,
        "```",
        "",
        "## Required by the brief",
        "",
        "- `2 Bears 1 Cave Ep. 344` in the copy and on the end card",
        "- `#2BearsWeekly` in the hashtags",
        "- `https://youtu.be/3pDAyRLPO58` in the account bio (account-level, not per post)",
        "",
        "## Gate",
        "",
        f"`{'PASS' if qc.get('ok') else 'FAIL'}` - "
        f"{sum(1 for c in qc.get('checks', []) if c['status'] == 'fail')} failure(s)",
        "",
    ]
    for check in qc.get("checks", []):
        body.append(f"- `{check['status']:>4}` {check['name']} - {check.get('detail', '')}")
    body += ["", "## Files", "",
             f"- `{slug}.mp4` - the master that ships",
             "- `cover.jpg` - 540x960 grid cover, from the clean graded base",
             "- `qc.json` - the gate's full report"]
    (folder / "POST.md").write_text("\n".join(body) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--video", help="default: <work>/job/final_s.mp4")
    args = ap.parse_args()

    work = Path(args.work)
    video = Path(args.video) if args.video else work / "job" / "final_s.mp4"
    if not video.exists():
        raise SystemExit(f"no finished render at {video}")
    timeline = json.loads((work / "timeline.json").read_text())
    folder = ROOT / "campaigns" / args.campaign / args.slug
    folder.mkdir(parents=True, exist_ok=True)
    master = folder / f"{args.slug}.mp4"
    shutil.copy2(video, master)

    # the cover comes from the CLEAN graded base, not the finished composite:
    # a densely captioned cut has no caption-free frame, and a cover with
    # subtitles across it is a screenshot, not a thumbnail
    treated = work / "job" / "base_treated.mp4"     # graded, uncaptioned
    clean = work / "base.mp4"                        # cut, uncaptioned
    source = treated if treated.exists() else (clean if clean.exists() else master)
    gaps = caption_gaps(timeline)
    if gaps:
        lo, hi = gaps[0]
        best = COV.best_frame(source, start=max(lo + 0.02, 0.2), end=max(hi - 0.02, 0.3))
    else:
        best = COV.best_frame(source, start=0.6)
    cap = cv2.VideoCapture(str(source))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(best["at"]) * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("could not read the cover frame")
    cv2.imwrite(str(folder / "cover.jpg"),
                cv2.resize(frame, (540, 960), interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 92])

    manifest_path = work / "gate_manifest.json"
    subprocess.run([sys.executable, str(ROOT / "scripts/whop/manifest_from_timeline.py"),
                    str(work), "--video", str(master)], check=True)
    report_path = work / "gate.json"
    gate = subprocess.run([sys.executable, str(ROOT / "scripts/whop/qc_gate.py"),
                           str(master), "--manifest", str(manifest_path),
                           "--campaign", args.campaign, "--out", str(report_path)],
                          text=True, capture_output=True)
    print(gate.stdout.strip() or gate.stderr.strip())
    report = json.loads(report_path.read_text())
    (folder / "qc.json").write_text(json.dumps(report, indent=1) + "\n")
    dur = float(timeline.get("duration") or 0.0)
    write_post(folder, timeline, args.slug, report, dur)
    print(f"{master}  cover {best['at']:.2f}s  gate "
          f"{'PASS' if report.get('ok') else 'FAIL'}  -> {folder / 'POST.md'}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
