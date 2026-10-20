#!/usr/bin/env python3
"""Render the whole drop in one command, and say what needs a human.

    .venv/bin/python scripts/whop/batch.py --campaign street_you_grew_up_on
    .venv/bin/python scripts/whop/batch.py --posts post6 post7 --ship

Each post is cut, gated and reported. A post that fails the gate is not a
crash - it is a line in the table with the reason, because the point of a
batch is to find the two clips that need attention without opening seven
tabs.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import tight_posts as TP   # noqa: E402


def posts_in(campaign: str) -> list[str]:
    folder = ROOT / "campaigns" / campaign
    return sorted(p.name for p in folder.glob("post*") if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default=TP.CAMPAIGN)
    ap.add_argument("--posts", nargs="*", help="default: every post* folder")
    ap.add_argument("--ship", action="store_true")
    ap.add_argument("--end", default="card", choices=["card", "peak"])
    args = ap.parse_args()

    todo = args.posts or posts_in(args.campaign)
    todo = [p for p in todo if p in TP.POSTS]
    if not todo:
        print("nothing to render: no post* folders with a POSTS entry")
        return 1

    rows = []
    for post in todo:
        t0 = time.time()
        try:
            rep = TP.build(post, ship=args.ship, end_mode=args.end)
            rows.append({"post": post, "ok": True,
                         "duration": rep.get("duration"),
                         "lufs": rep.get("lufs"), "dbtp": rep.get("dbtp"),
                         "secs": round(time.time() - t0, 1),
                         "notes": ", ".join(
                             f"{k}={'use' if v.get('use') else 'skip'}"
                             for k, v in rep.get("direction", {}).items())})
        except SystemExit as exc:
            rows.append({"post": post, "ok": False, "error": str(exc),
                         "secs": round(time.time() - t0, 1)})
        except Exception as exc:                       # noqa: BLE001 - a batch reports, never dies
            rows.append({"post": post, "ok": False, "error": repr(exc),
                         "secs": round(time.time() - t0, 1)})

    print("\nBATCH")
    print(f"{'post':8s} {'result':7s} {'dur':>6s} {'LUFS':>7s} {'dBTP':>6s} {'secs':>6s}")
    for r in rows:
        if r["ok"]:
            print(f"{r['post']:8s} {'ok':7s} {r['duration']:6.2f} "
                  f"{r['lufs']:7.1f} {r['dbtp']:6.1f} {r['secs']:6.1f}")
        else:
            print(f"{r['post']:8s} {'FAIL':7s} {'-':>6s} {'-':>7s} {'-':>6s} "
                  f"{r['secs']:6.1f}  {r['error'][:60]}")
    print("\nGate each output with:")
    print("  .venv/bin/python scripts/whop/qc_gate.py <file> --manifest work/street/<post>/tight_cards.json")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
