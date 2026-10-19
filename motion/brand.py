#!/usr/bin/env python3
"""Auto-brand: measure a video's dominant colours, pick the closest
theme (hue family) and suggest an accent override from the footage
itself. No strong colour found -> the theme's own accent stays.

Usage: python motion/brand.py <video.mp4>   (prints JSON)
"""
from __future__ import annotations

import colorsys
import json
import sys
from pathlib import Path

import cv2
import numpy as np

THEMES = Path(__file__).resolve().parent / "themes"


def dominant_palette(video: Path, n: int = 9) -> list[dict]:
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    px = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (k + 0.5) / n))
        ok, fr = cap.read()
        if ok:
            px.append(cv2.resize(fr, (96, 170)).reshape(-1, 3))
    cap.release()
    data = np.vstack(px).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.8)
    _, labels, centres = cv2.kmeans(data, 6, None, criteria, 3,
                                    cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=6)
    out = []
    for c, cnt in zip(centres, counts):
        b, g, r = (float(x) / 255 for x in c)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        out.append({"rgb": [round(r * 255), round(g * 255),
                            round(b * 255)],
                    "hue": round(h * 360), "sat": round(s, 2),
                    "val": round(v, 2), "share": round(float(cnt) / len(data), 3)})
    return sorted(out, key=lambda d: -d["share"])


def pick_theme(palette: list[dict]) -> dict:
    themes = {p.stem: theme for p in sorted(THEMES.glob("*.json"))
              if isinstance((theme := json.loads(p.read_text())).get("accent"), str)
              and len(theme["accent"]) == 7 and theme["accent"].startswith("#")}
    if not themes:
        raise ValueError("no auto-brand themes with a configured hue")
    # accent candidate: most saturated, reasonably bright, real share
    cand = [c for c in palette if c["sat"] > 0.45 and c["val"] > 0.35
            and c["share"] > 0.02]
    accent = None
    if cand:
        best = max(cand, key=lambda c: c["sat"] * c["share"])
        accent = "#%02X%02X%02X" % tuple(best["rgb"])
        hue = best["hue"]
    else:
        hue = max(palette, key=lambda c: c["share"])["hue"]
    def theme_hue(t):
        r, g, b = (int(t["accent"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hsv(r, g, b)[0] * 360
    name = min(themes, key=lambda nm: min(
        abs(theme_hue(themes[nm]) - hue), 360 - abs(theme_hue(themes[nm]) - hue)))
    return {"theme": name, "accent_override": accent,
            "basis_hue": hue, "palette": palette[:4]}


def main() -> int:
    print(json.dumps(pick_theme(dominant_palette(Path(sys.argv[1]))),
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
