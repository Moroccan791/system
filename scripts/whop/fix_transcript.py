#!/usr/bin/env python3
"""Repair the words a speech recogniser got wrong, without moving time.

    .venv/bin/python scripts/whop/fix_transcript.py <in.json> <out.json> corrections.json

Captions are verbatim, so a wrong word is not a typo - it is the wrong thing on
screen, and "are you dead machine?" for "are you Bert Kreischer?" is the kind of
error that makes a clip look machine-made to anybody watching.

The rules are deliberately narrow. Each one replaces a run of words the
recogniser produced and a person would not have said (a non-word, a word
doubled by the decoder, a name it could not resolve) with the run that was
actually spoken. Times are kept: the replacement is spread across the span of
the words it replaces, so nothing downstream - card times, punch times, the
bed's ducking - shifts by a frame.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

STRIP = re.compile(r"[^a-z0-9']+")


def norm(text: str) -> str:
    return STRIP.sub("", str(text).lower())


def apply(words: list[dict], rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply each rule once, at its first match. Returns (words, applied)."""
    out = list(words)
    applied: list[dict] = []
    for rule in rules:
        find = [norm(t) for t in rule["find"]]
        repl = list(rule["replace"])
        n = len(find)
        for i in range(len(out) - n + 1):
            if [norm(w["text"]) for w in out[i:i + n]] != find:
                continue
            span = out[i:i + n]
            t0, t1 = float(span[0]["start"]), float(span[-1]["end"])
            step = (t1 - t0) / max(len(repl), 1)
            new = [{"text": tok, "start": round(t0 + k * step, 3),
                    "end": round(t0 + (k + 1) * step, 3)}
                   for k, tok in enumerate(repl)]
            out[i:i + n] = new
            applied.append({"at": t0, "was": " ".join(w["text"] for w in span),
                            "now": " ".join(repl)})
            break
    return out, applied


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("rules")
    args = ap.parse_args()
    data = json.loads(Path(args.source).read_text())
    rules = json.loads(Path(args.rules).read_text())
    words, applied = apply(data["words"], rules)
    data["words"] = words
    data["corrections"] = len(applied)
    Path(args.out).write_text(json.dumps(data))
    for row in applied:
        print(f"  {row['at']:8.2f}s  {row['was']!r} -> {row['now']!r}")
    print(f"{len(applied)} of {len(rules)} rules applied -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
