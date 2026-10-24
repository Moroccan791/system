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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.whop import runtime

ROOT = Path("/home/user/system")
# The interpreter running this script, not a directory name that happens to
# exist on one machine. See scripts/whop/runtime.py.
PY = runtime.python_exe()
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
    dest = ROOT / "campaigns" / campaign / post
    theme_file = ROOT / "motion" / "themes" / f"{campaign}__{post}.json"

    # A saved card for this exact video is a hard production prerequisite.
    # Never copy the campaign palette or another video's theme into this post.
    sys.path.insert(0, str(ROOT))
    from scripts.whop.style_card import is_style_approved
    if not is_style_approved(campaign, post):
        raise SystemExit(f"EDIT BLOCKED: approve fonts and colours first at "
                         f"scripts/whop/style_card.py serve --campaign {campaign} "
                         f"--video {post}")
    try:
        approved_theme = json.loads(theme_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"EDIT BLOCKED: approved per-video theme missing: {theme_file}") from exc
    card = approved_theme.get("styleCard") or {}
    if not (card.get("approved") is True and card.get("campaign") == campaign
            and card.get("video") == post and card.get("style_sha256")
            and is_style_approved(campaign, post, card.get("style_sha256"))):
        raise SystemExit("EDIT BLOCKED: theme does not match this video's approval receipt")

    work = ROOT / "work" / "street" / post
    work.mkdir(parents=True, exist_ok=True)

    # 1. spec
    run([PY, ROOT / "scripts/whop/build_whop_clip.py", plan_path])
    # 2. the cut
    run([PY, ROOT / "scripts/whop/tight_base.py", work / "spec.json"])
    # 3. the timeline, now on the cut's own word clock
    run([PY, ROOT / "scripts/whop/build_whop_clip.py", plan_path])
    # 4. validate
    run([PY, ROOT / "motion/validate.py", work / "timeline.json"])

    # 5. render
    env = runtime.render_env()
    theme = ROOT / "motion" / "themes" / f"{campaign}__{post}"
    music = ROOT / "assets" / "music" / plan.get("music", "chill.wav")
    run([PY, ROOT / "motion/produce.py", work / "timeline.json", work / "base.mp4",
         work / "slice.json", work / "job", "--theme", theme, "--music", music,
         "--style-campaign", campaign, "--style-video", post],
        env=env)

    # 6. picture QC
    run([PY, ROOT / "scripts/whop/check.py", work / "job" / "final_s.mp4"])

    # 6b. campaign gate: the rules from the clipping course, judged on the
    # rendered file itself (caption length, fillers, hook, loudness, true
    # peak, voice over the bed, bars, caption over a face, frozen frames,
    # tail). It reads the job's own timeline/slice, so it grades what is on
    # screen, not what the plan intended. A demo render may only warn.
    gate_manifest = work / "gate_manifest.json"
    run([PY, ROOT / "scripts/whop/manifest_from_timeline.py", work,
         "--video", work / "job" / "final_s.mp4", "--out", gate_manifest])
    gate_cmd = [PY, ROOT / "scripts/whop/qc_gate.py", work / "job" / "final_s.mp4",
                "--manifest", gate_manifest, "--campaign", campaign]
    if post.endswith("_demo"):
        gate_cmd.append("--warn-only")
    run(gate_cmd)

    # 7. deliver without touching another post's shipped folder
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"street_{post}.mp4"
    shutil.copy2(work / "job" / "final_s.mp4", out)
    demo_only = post.endswith("_demo")
    label = "internal demo rendered" if demo_only else "shipped"
    print(f"\n{label} {out} ({out.stat().st_size} bytes)")

    # 8. the posting pack
    post_md = plan.get("posting")
    if post_md:
        disclosure = post_md.get("disclosure", "#ad").strip()
        description = post_md.get("description", "").strip()
        if disclosure and disclosure.casefold() not in description.casefold():
            description = f"{disclosure}\n{description}".strip()
        lines = [f"# {post.upper()} - posting pack", "",
                 f"**File:** `street_{post}.mp4`", "",
                 "## Title", "", post_md["title"], "",
                 "## Description (copy-paste exactly)", "", description, "",
                 post_md.get("requiredLine", ""), "",
                 "## Hashtags", "",
                 " ".join(post_md.get("hashtags", [])), "",
                 "## Notes", ""]
        if demo_only:
            lines.append("- Internal demo preview only; not approved to publish.")
        lines.extend([f"- Disclosure: {disclosure}",
                      "- Full episode: the podcast is the source; this is a clipped edit.", ""])
        (dest / "POST.md").write_text("\n".join(lines))
        print(f"wrote {dest / 'POST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
