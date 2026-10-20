#!/usr/bin/env python3
"""Close the loop: let the numbers argue with the rubric.

Everything else in this pipeline is a considered guess - the hook floor of
4.0, the punch density, the length window. A guess becomes a rule only when
something outside agrees with it, and the only outside signal is how the posts
actually did.

This reads the campaign's own results table and asks one question: **does the
hook score predict anything?** If posts that scored higher opened better, the
rubric is measuring something real and the floor is meaningful. If it does
not, the honest output is that the floor is decoration and should be rebuilt -
not that the numbers are wrong.

Input is deliberately boring, so it can be filled in by hand from the app:

    post, hook_score, views, watched_3s, duration
    post4, 7.2, 120000, 0.71, 22.9
    ...

`watched_3s` is a fraction (0.71) or a percentage (71); both are accepted.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s or s in {"-", "—", "n/a", "NA"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_table(path: Path) -> list[dict]:
    """CSV, or the markdown table in RESULTS.md. Same rows either way."""
    text = path.read_text()
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
    else:
        rows = []
        header: list[str] | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header is None:
                header = [c.lower() for c in cells]
                continue
            rows.append(dict(zip(header, cells)))
    out = []
    for r in rows:
        clean = {str(k).strip().lower(): v for k, v in r.items() if k}
        rec = {
            "post": str(clean.get("post", "")).strip(),
            "hook": _num(clean.get("hook_score") or clean.get("hook")),
            "views": _num(clean.get("views")),
            "watched_3s": _num(clean.get("watched_3s") or clean.get("retention_3s")),
            "duration": _num(clean.get("duration")),
        }
        if rec["watched_3s"] is not None and rec["watched_3s"] > 1.5:
            rec["watched_3s"] = rec["watched_3s"] / 100.0     # 71 -> 0.71
        if rec["post"]:
            out.append(rec)
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation: views are heavy-tailed, so ranks, not values."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) ** 0.5) * (sum((b - my) ** 2 for b in ry) ** 0.5)
    return None if den == 0 else round(num / den, 3)


def analyse(rows: list[dict], floor: float = 4.0) -> dict:
    usable = [r for r in rows if r["hook"] is not None and r["watched_3s"] is not None]
    out: dict = {"posts": len(rows), "usable": len(usable)}
    if len(usable) < 3:
        out["verdict"] = ("not enough posts with numbers yet - the rubric stands "
                          "on its reference calibration until there are three")
        out["correlation"] = None
        return out

    xs = [r["hook"] for r in usable]
    ys = [r["watched_3s"] for r in usable]
    rho = spearman(xs, ys)
    above = [r["watched_3s"] for r in usable if r["hook"] >= floor]
    below = [r["watched_3s"] for r in usable if r["hook"] < floor]
    out.update({
        "correlation": rho,
        "above_floor_mean": round(sum(above) / len(above), 3) if above else None,
        "below_floor_mean": round(sum(below) / len(below), 3) if below else None,
        "best": max(usable, key=lambda r: r["watched_3s"])["post"],
        "worst": min(usable, key=lambda r: r["watched_3s"])["post"],
    })
    if rho is None:
        out["verdict"] = "no spread in the hook scores - nothing to learn yet"
    elif rho >= 0.5:
        out["verdict"] = (f"the rubric predicts retention (rho={rho:+.2f}); keep "
                          f"the {floor} floor")
    elif rho <= -0.2:
        out["verdict"] = (f"the rubric is backwards (rho={rho:+.2f}) - rebuild the "
                          f"weights before trusting the floor")
    else:
        out["verdict"] = (f"no clear link (rho={rho:+.2f}) - the hook score is not "
                          f"what is deciding these, look at pacing and sound first")
    if above and below:
        out["floor_check"] = round((sum(above) / len(above)) - (sum(below) / len(below)), 3)
    return out


def append_row(path: Path, *, post: str, hook: float, views: int,
               watched_3s: float, duration: float) -> Path:
    """Add one measured post to the table, so the loop can start.

    Writing the row is the hard part in practice - it is the step that gets
    skipped - so it takes one command and refuses to double-add a post.
    """
    text = path.read_text() if path.exists() else "# Results\n\n"
    lines = text.splitlines()
    header_at = next((i for i, ln in enumerate(lines)
                      if ln.strip().startswith("|") and "post" in ln.lower()
                      and "hook" in ln.lower()), None)
    if header_at is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", "| post | hook_score | views | watched_3s | duration |",
                  "|---|---|---|---|---|"]
        header_at = len(lines) - 2
    if any(ln.split("|")[1].strip() == post for ln in lines[header_at:]
           if ln.strip().startswith("|") and len(ln.split("|")) > 1):
        raise SystemExit(f"{post} is already in {path} - edit the row instead")
    row = f"| {post} | {hook:g} | {views} | {watched_3s:g} | {duration:g} |"
    insert_at = header_at + 2
    while insert_at < len(lines) and lines[insert_at].strip().startswith("|"):
        insert_at += 1
    lines.insert(insert_at, row)
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", help="RESULTS.md or a .csv")
    ap.add_argument("--floor", type=float, default=4.0)
    ap.add_argument("--json", help="write the analysis here")
    ap.add_argument("--add", nargs=4, metavar=("POST", "HOOK", "VIEWS", "WATCHED_3S"),
                    help="append a measured post, e.g. --add post7 5.0 120000 0.61")
    ap.add_argument("--duration", type=float, default=22.0)
    args = ap.parse_args()
    if args.add:
        post, hook, views, watched = args.add
        append_row(Path(args.results), post=post, hook=float(hook),
                   views=int(float(views)), watched_3s=float(watched),
                   duration=args.duration)
        print(f"added {post} to {args.results}")
    rows = parse_table(Path(args.results))
    out = analyse(rows, args.floor)
    print(json.dumps(out, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
