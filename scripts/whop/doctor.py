#!/usr/bin/env python3
"""Can this machine make a post right now? Ask before spending an evening.

    python scripts/whop/doctor.py                    # everything
    python scripts/whop/doctor.py --post post6       # one post
    python scripts/whop/doctor.py --campaign street_you_grew_up_on
    python scripts/whop/doctor.py --new-campaign my_campaign

A whop post needs five things that all live outside git: an interpreter with
the packages, the source footage, the transcript the captions are timed from,
an approved style card, and a plan. Any one missing stops the chain — usually
twenty minutes in, after the slow part. This checks all five in two seconds and
prints the command that fixes each one.

Exit code is 1 if anything is BLOCKING, so it can gate a batch the way
preflight.py gates a raw.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.whop import runtime  # noqa: E402

OK, WARN, BLOCK = "OK", "WARN", "BLOCK"


@dataclass
class Check:
    name: str
    state: str
    detail: str
    fix: str = ""

    def line(self) -> str:
        return f"[{self.state:5s}] {self.name:22s} {self.detail}"


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, *a, **kw) -> Check:
        c = Check(*a, **kw)
        self.checks.append(c)
        return c

    @property
    def blocking(self) -> list[Check]:
        return [c for c in self.checks if c.state == BLOCK]


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------
def check_env(rep: Report) -> None:
    deps = runtime.missing_deps()
    rep.add("interpreter", OK, runtime.python_exe())
    if deps:
        rep.add("packages", BLOCK,
                "missing " + ", ".join(m for m, _ in deps),
                "pip install " + " ".join(p for _, p in deps)
                + "   (or: bash scripts/whop/restore.sh)")
    else:
        rep.add("packages", OK, "numpy, pillow, cv2, jsonschema")


def check_plan(rep: Report, plan_path: Path) -> dict | None:
    if not plan_path.exists():
        rep.add("plan", BLOCK, _rel(plan_path),
                "write it with scripts/whop/mkplan.py, or point --post at a "
                "plan that exists in scripts/whop/plans/")
        return None
    try:
        plan = json.loads(plan_path.read_text())
    except json.JSONDecodeError as exc:
        rep.add("plan", BLOCK, f"{_rel(plan_path)} is not valid JSON ({exc})")
        return None
    rep.add("plan", OK, f"{_rel(plan_path)} ({plan.get('post', '?')})")
    return plan


def check_source(rep: Report, plan: dict) -> None:
    src = ROOT / plan.get("source", "work/street/raw/street_full.mp4")
    if src.exists():
        mb = src.stat().st_size / 1e6
        rep.add("source footage", OK, f"{_rel(src)} ({mb:.0f} MB)")
        return
    # name the release that carries it, so the fix is a copy-paste
    name = src.name
    rep.add("source footage", BLOCK, f"{_rel(src)} is not here",
            f"the sandbox loses work/ on a reset. Fetch it back:\n"
            f"    bash scripts/whop/restore.sh          # the street episode\n"
            f"    or, for a release asset:  doctor.py --fetch {name}")


def check_transcript(rep: Report, plan: dict) -> None:
    t = plan.get("transcript")
    if not t:
        rep.add("transcript", WARN, "the plan does not name one",
                "captions are timed from it; set \"transcript\" in the plan")
        return
    path = ROOT / t
    if path.exists():
        try:
            d = json.loads(path.read_text())
            n = len(d.get("words") or d.get("segments") or [])
            rep.add("transcript", OK, f"{_rel(path)} ({n} tokens)")
        except json.JSONDecodeError:
            rep.add("transcript", BLOCK, f"{_rel(path)} is not valid JSON")
        return
    rep.add("transcript", BLOCK, f"{_rel(path)} is not here",
            "transcripts live in work/ too. Rebuild with:\n"
            "    python scripts/whop/transcribe_episode.py <audio-or-video>\n"
            "    (ASR runs in CI: .github/workflows/asr-words.yml)")


def check_style(rep: Report, campaign: str, post: str) -> None:
    try:
        from scripts.whop.style_card import is_style_approved
    except Exception as exc:                       # cv2 etc.
        rep.add("style card", WARN, f"could not import style_card ({exc})")
        return
    if is_style_approved(campaign, post):
        rep.add("style card", OK, f"{campaign}/{post} approved")
    else:
        rep.add("style card", BLOCK, f"{campaign}/{post} is not approved",
                f"python scripts/whop/style_card.py serve --campaign "
                f"{campaign} --video {post}\n"
                f"    (the render refuses to run without the saved receipt — "
                f"that is deliberate, the face and colours are the operator's)")


def check_theme(rep: Report, campaign: str, post: str) -> None:
    p = ROOT / "motion" / "themes" / f"{campaign}__{post}.json"
    if p.exists():
        rep.add("theme", OK, _rel(p))
    else:
        rep.add("theme", BLOCK, f"{_rel(p)} is missing",
                f"python scripts/whop/font_refresh.py {post}   # or approve a "
                f"style card, which writes it")


def check_post(rep: Report, campaign: str, post: str,
               plan_path: Path) -> None:
    plan = check_plan(rep, plan_path)
    if plan is None:
        return
    check_source(rep, plan)
    check_transcript(rep, plan)
    check_style(rep, campaign, post)
    check_theme(rep, campaign, post)


def check_campaign(rep: Report, campaign: str) -> None:
    d = ROOT / "campaigns" / campaign
    if not d.exists():
        rep.add("campaign", BLOCK, _rel(d),
                "make it, with brief.md and campaign_rules.json — the gate "
                "reads the rules from there")
        return
    rep.add("campaign", OK, _rel(d))
    for want in ("campaign_rules.json", "brief.md"):
        rep.add(want, OK if (d / want).exists() else WARN,
                "present" if (d / want).exists() else "missing")


def check_new_campaign(rep: Report, name: str) -> None:
    """What a campaign needs before its first post can be cut."""
    check_campaign(rep, name)
    plans = sorted((ROOT / "scripts" / "whop" / "plans").glob("*.json"))
    rep.add("plans", OK if plans else WARN, f"{len(plans)} on file")
    check_env(rep)
    # what a new campaign is missing is unavoidable: its own footage.
    rep.add("source footage", WARN,
            "a new campaign needs its raw before anything else",
            "drop it on a release, then fetch it:\n"
            "    doctor.py --fetch <asset-name> --release <tag>\n"
            "    (or push .github/footage-request.json and let CI pull it)")


def write_fetch_request(asset: str, release: str, out_dir: str) -> Path:
    """Emit the request file that fires .github/workflows/fetch.yml."""
    req = {"tag": release, "pattern": asset, "out_dir": out_dir}
    p = ROOT / ".github" / "footage-request.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(req, indent=1) + "\n")
    return p


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="is this machine ready to cut?")
    ap.add_argument("--campaign", default="street_you_grew_up_on")
    ap.add_argument("--post", default=None)
    ap.add_argument("--new-campaign", default=None, metavar="NAME")
    ap.add_argument("--fetch", default=None, metavar="ASSET",
                    help="write the CI fetch request for this release asset")
    ap.add_argument("--release", default="footage-demi-1")
    ap.add_argument("--out-dir", default="work/fetch")
    ap.add_argument("--only-env", action="store_true")
    a = ap.parse_args(argv)

    rep = Report()
    if a.fetch:
        p = write_fetch_request(a.fetch, a.release, a.out_dir)
        print(f"wrote {_rel(p)} — it points at {a.release}/{a.fetch}")
        print("  commit and push it; .github/workflows/fetch.yml will pull the "
              "asset into the branch")
        return 0

    check_env(rep)
    if not a.only_env:
        if a.new_campaign:
            check_new_campaign(rep, a.new_campaign)
        elif a.post:
            check_post(rep, a.campaign, a.post,
                       ROOT / "scripts" / "whop" / "plans" / f"{a.post}.json")
        else:
            check_campaign(rep, a.campaign)

    print()
    for c in rep.checks:
        print(c.line())
    if rep.blocking:
        print("\nto fix:")
        seen = set()
        for c in rep.blocking:
            if c.fix and c.fix not in seen:
                seen.add(c.fix)
                print(f"  {c.name}: {c.fix}")
        print(f"\n{len(rep.blocking)} blocking. Not ready to cut.")
        return 1
    print("\nready to cut.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
