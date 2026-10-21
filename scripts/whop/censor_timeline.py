#!/usr/bin/env python3
"""Star 18+ words in a motion timeline, before it is rendered.

The house rule is display-only: `clipper.captions.block.censor_text` stars the
second letter of an 18+ token ("sex" -> "s*x", "Fuck" -> "F*ck") so the caption
still reads at speed and the platform still sees safe text. That function lives
in the caption stack, and the motion path (`build_whop_clip` -> `produce`) does
not go through it - so a clip rendered through the graphics layer could ship the
raw word. `build_whop_clip` masks as it builds; this masks a timeline that was
already written (an old job, a hand-edited file), so both are covered.

    python scripts/whop/censor_timeline.py work/<post>/timeline.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from clipper.captions.block import censor_text  # noqa: E402

TEXT_KEYS = ("w", "text", "label", "title", "sub", "by")


def _walk(node, hits: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in TEXT_KEYS and isinstance(v, str) and v.strip():
                masked = censor_text(v)
                if masked != v:
                    hits.append((v, masked))
                    node[k] = masked
            else:
                _walk(v, hits)
    elif isinstance(node, list):
        for v in node:
            _walk(v, hits)


def main() -> int:
    path = Path(sys.argv[1])
    tl = json.loads(path.read_text())
    hits: list[tuple[str, str]] = []
    _walk(tl.get("items") or [], hits)
    if hits:
        path.write_text(json.dumps(tl, indent=1) + "\n")
    print(f"{len(hits)} masked" + (": " + ", ".join(f"{a}->{b}" for a, b in hits)
                                   if hits else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
