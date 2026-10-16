#!/usr/bin/env python3
"""Font packs: list what you can choose from, per video.

    python motion/fonts.py            # the menu
    produce.py ... --font anton       # use one for a whole video

Packs are whole-video choices (a video has ONE display voice, the
same way it has one accent). Themes may declare a pack; the
--font flag overrides it. All faces are OFL-1.1, vendored in
assets/fonts/ (fontsource builds), so renders stay offline and
deterministic forever.
"""
from __future__ import annotations

import sys

PACKS = [
    ("montserrat", "Montserrat ExtraBold (the default workhorse)",
     "safe, punchy, reads at any size - business, explainers, "
     "anything you'd ship without thinking twice"),
    ("anton", "Anton (tall condensed caps)",
     "the big-statement look: hooks, hero words, sports/hustle "
     "energy. Words render ALL-CAPS and narrow, so phrases fit "
     "more width - great for behind-the-person heroes"),
    ("bebas", "Bebas Neue (clean tall caps)",
     "lighter than Anton, more editorial: fitness, food, travel, "
     "lifestyle. Also all-caps by design"),
    ("grotesk", "Space Grotesk Bold",
     "techy, geometric, slightly futuristic: AI, startups, money "
     "systems. Keeps lowercase, so captions stay natural"),
    ("serif", "Playfair Display Bold (+italic)",
     "premium/elegant: finance, luxury, reflective stories. The "
     "italic is built in for the soft-word contrast"),
    ("archivo", "Archivo Black (the caption-tool classic)",
     "the chunky poster caps behind half the big-editor look: "
     "karaoke stacks, hero words, hooks. Very wide - heroes earn "
     "their shrink-to-fit. If you want 'that Moonshot-caption "
     "feel', this is usually the one"),
    ("poppins", "Poppins ExtraBold",
     "rounded, friendly, modern: lifestyle, coaching, education. "
     "Keeps lowercase, softer than the caps packs"),
    ("luckiest", "Luckiest Guy",
     "playful cartoon display: comedy, gaming, kids, high-energy "
     "hooks only - use sparingly, it shouts"),
]


def main() -> int:
    print("FONT PACKS - choose per video with:  produce.py --font <name>\n")
    for name, face, vibe in PACKS:
        print(f"  {name:<11} {face}\n  {'':<11} {vibe}\n")
    print("Themes karaoke-bold / bounce-party / neon-nights carry "
          "anton / bebas / grotesk out of the box.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
