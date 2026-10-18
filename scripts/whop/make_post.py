#!/usr/bin/env python3
"""Build and ship one whop clip from a plan.

    python scripts/whop/make_post.py scripts/whop/plans/post2.json

Chain (strictly sequential - a render that races the edit ships a
stale cut):
    1. plan  -> spec.json          (source window, drops, crops)
    2. tight_base.py spec.json     -> base.mp4 + slice.json (the cut)
    3. plan  -> timeline.json       (captions/graphics on the cut's clock)
    4. validate.py timeline.json
    5. produce.py                   -> job/final.mp4 + job/final_s.mp4
    6. check.py job/final_s.mp4     (the picture QC gate)
    7. copy to campaigns/<campaign>/<post>/ + write POST.md
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/user/system")
PY = str(ROOT / ".venv/bin/python")
CAMPAIGNS = ROOT / "campaigns" / "street_you_grew_up_on"


def run(cmd, env=None, cwd=ROOT):
    print("\n$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                       capture_output=True, text=True)
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-25:])
    print(tail)
    if r.returncode != 0:
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(str(c) for c in cmd)}")
    return r.stdout


def main() -> int:
    plan_path = Path(sys.argv[1])
    plan = json.loads(plan_path.read_text())
    post = plan["post"]
    campaign = plan.get("campaign", "street_you_grew_up_on")
    work = ROOT / "work" / "street" / post
    work.mkdir(parents=True, exist_ok=True)

    # 0. the per-post style (the user picks the fonts and the colours
    #    BEFORE the edit - the style card writes it, we only seed it
    #    from the campaign style when the post is new)
    dest = CAMPAIGNS / post
    dest.mkdir(parents=True, exist_ok=True)
    style_src = CAMPAIGNS / "style.json"
    style_dst = dest / "style.json"
    if not style_dst.exists() and style_src.exists():
        shutil.copy2(style_src, style_dst)
        print(f"seeded {style_dst}")
    theme_file = ROOT / "motion" / "themes" / f"{campaign}__{post}.json"
    if not theme_file.exists():
        base_theme = ROOT / "motion" / "themes" / f"{campaign}__post1.json"
        if not base_theme.exists():
            base_theme = ROOT / "motion" / "themes" / f"{campaign}.json"
        if base_theme.exists():
            shutil.copy2(base_theme, theme_file)
            print(f"seeded {theme_file}")

    # 1. spec
    run([PY, ROOT / "scripts/whop/build_whop_clip.py", plan_path])
    # 2. the cut
    run([PY, ROOT / "scripts/whop/tight_base.py", work / "spec.json"])
    # 3. the timeline, now on the cut's own word clock
    run([PY, ROOT / "scripts/whop/build_whop_clip.py", plan_path])
    # 4. validate
    run([PY, ROOT / "motion/validate.py", work / "timeline.json"])

    # 5. render
    import os
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = "/tmp/al2023/lib"
    theme = ROOT / "motion" / "themes" / f"{campaign}__{post}"
    music = ROOT / "assets" / "music" / plan.get("music", "chill.wav")
    run([PY, ROOT / "motion/produce.py", work / "timeline.json", work / "base.mp4",
         work / "slice.json", work / "job", "--theme", theme, "--music", music],
        env=env)

    # 6. picture QC
    run([PY, ROOT / "scripts/whop/check.py", work / "job" / "final_s.mp4"])

    # 7. ship
    out = dest / f"street_{post}.mp4"
    shutil.copy2(work / "job" / "final_s.mp4", out)
    print(f"\nshipped {out} ({out.stat().st_size} bytes)")

    # 8. the posting pack
    post_md = plan.get("posting")
    if post_md:
        lines = [f"# {post.upper()} - posting pack", "",
                 f"**File:** `street_{post}.mp4`", "",
                 "## Title", "", post_md["title"], "",
                 "## Description", "",
                 post_md.get("description", ""), "",
                 post_md.get("requiredLine", ""), "",
                 "## Hashtags", "",
                 " ".join(post_md.get("hashtags", [])), "",
                 "## Notes", "",
                 f"- Disclosure: {post_md.get('disclosure', '#ad')}",
                 "- Full episode: the podcast is the source; this is a clipped edit.",
                 ""]
        (dest / "POST.md").write_text("\n".join(lines))
        print(f"wrote {dest / 'POST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
