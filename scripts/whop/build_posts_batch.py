#!/usr/bin/env python3
"""Build the selected Street You Grew Up On shorts, serially.

For each post: recompute face-aware 9:16 crops, save them into the plan,
run the complete plan->cut->timeline->QC->posting-pack pipeline, and
refresh a cover frame. Serial rendering keeps the two-CPU workspace
stable. A failed post is logged and the remaining plans still run.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
DEFAULT_POSTS = [f"post{i}" for i in range(2, 8)]
REQUIRED_LINE = (
    "The podcast name is Street You Grew Up On - full episode is available "
    "on YT and other podcast platforms"
)


def run(post: str, step: str, cmd: list[str]) -> None:
    log = ROOT / "work" / "street" / post / f"{step}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as f:
        p = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                           text=True)
    tail = "\n".join(log.read_text(errors="replace").splitlines()[-18:])
    print(f"\n=== {post} / {step} (exit {p.returncode}) ===\n{tail}", flush=True)
    if p.returncode:
        raise RuntimeError(f"{post} {step} failed; see {log}")


def verify_pack(post: str) -> None:
    dest = ROOT / "campaigns" / "street_you_grew_up_on" / post
    md = (dest / "POST.md").read_text()
    if REQUIRED_LINE not in md:
        raise RuntimeError(f"{post}: required campaign description line missing")
    section = md.split("## Hashtags", 1)[-1].split("## Notes", 1)[0]
    tags = [x for x in section.split() if x.startswith("#")]
    if not 7 <= len(tags) <= 8:
        raise RuntimeError(f"{post}: expected 7-8 hashtags, found {len(tags)}")
    desc = md.split("## Description", 1)[-1].split("## Hashtags", 1)[0]
    if "#ad" not in desc and "#sponsored" not in desc:
        raise RuntimeError(f"{post}: disclosure missing from copy-paste description")


def refresh_cover(post: str) -> None:
    import cv2

    source = ROOT / "work" / "street" / post / "job" / "final_s.mp4"
    dest = ROOT / "campaigns" / "street_you_grew_up_on" / post / "cover.jpg"
    cap = cv2.VideoCapture(str(source))
    # Take a clean hook frame after the opening word has settled, before
    # any title card or vector scene can cover the speaker.
    cap.set(cv2.CAP_PROP_POS_MSEC, 650)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"{post}: could not extract cover frame")
    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (540, 960), interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise RuntimeError(f"{post}: could not write {dest}")


def main() -> int:
    posts = sys.argv[1:] or DEFAULT_POSTS
    failures: list[str] = []
    for post in posts:
        try:
            plan_path = ROOT / "scripts" / "whop" / "plans" / f"{post}.json"
            plan = json.loads(plan_path.read_text())
            if plan.get("post") != post:
                raise RuntimeError(f"plan identity mismatch: {plan_path}")
            style = ROOT / "campaigns" / "street_you_grew_up_on" / post / "style.json"
            theme = ROOT / "motion" / "themes" / f"street_you_grew_up_on__{post}.json"
            if not style.exists() or not theme.exists():
                raise RuntimeError(f"{post}: per-post approved style/theme is missing")

            start, end = map(float, plan["span"])
            cuts = ",".join(str(float(x)) for x in plan.get("splits", []))
            run(post, "crops", [str(PY), "scripts/whop/face_crops.py",
                                 "--start", str(start), "--end", str(end),
                                 "--cuts", cuts, "--post", post])
            crops_path = ROOT / "work" / "street" / post / "crops.json"
            plan["crops"] = json.loads(crops_path.read_text())
            plan_path.write_text(json.dumps(plan, indent=2) + "\n")

            run(post, "build", [str(PY), "scripts/whop/make_post.py",
                                 str(plan_path)])
            verify_pack(post)
            refresh_cover(post)
            print(f"\n{post}: delivered video, cover, style card and posting pack\n",
                  flush=True)
        except Exception as exc:
            failures.append(f"{post}: {exc}")
            print(f"\nFAILED {post}: {exc}\n", file=sys.stderr, flush=True)
    print("\nBATCH SUMMARY")
    print("failed:", " | ".join(failures) if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
