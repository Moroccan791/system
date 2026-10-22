"""Which moments in a pack are worth cutting to?

An edit is only as good as the frames it chooses, and a two-minute pack has maybe
eight moments that carry a cut. Finding them by scrubbing is the slowest part of
the job and the one most likely to be done in a hurry, so it is a stage.

`rank()` scores every shot on what actually survives a 0.4-second cut:

  * **motion** — a still frame at 0.4s is a photograph, not a shot. Weighted
    highest, because the reference edit is motion-first.
  * **sharpness** — a blurred frame is fine for a whip and wrong for a hold.
  * **brightness** — the drop wants frames that separate from the plate behind
    the type; a frame at 18/255 disappears under a white word.
  * **length** — under ~0.6s a shot cannot hold a word; over ~6s it is a scene,
    not a moment.

Scores are percentile-ranked against the pack itself, never against a constant,
so the ranking means the same thing on a dark film and a bright one.

`sheet()` renders the shortlist as a contact sheet with timecodes — the thing an
editor actually decides from. Cutting from a number alone is how you end up with
eight technically-sharp frames of the same empty hallway.
"""
from __future__ import annotations

import json
from pathlib import Path

from .shots import Shot, analyse


def _pct(values: list[float]) -> list[float]:
    """Percentile rank, 0..1. A pack defines its own scale."""
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    for rank, i in enumerate(order):
        out[i] = rank / max(1, len(values) - 1)
    return out


def rank(src, top: int = 8, min_dur: float = 0.55, max_dur: float = 8.0,
         only: list[int] | None = None, avoid: list[int] | None = None) -> list[dict]:
    """Rank the pack, optionally inside the brief's shot class.

    `only` / `avoid` are what stops this module from repeating the mistake that
    created brief.py: a scorer that likes movement hands you Spider-Man swinging
    when the song is about the two of them. Score geometry, then let the brief
    decide which shots are on subject.
    """
    shots: list[Shot] = [s for s in src.shots if min_dur <= s.dur <= max_dur] or src.shots
    if only:
        allowed = set(only)
        shots = [s for s in shots if s.index in allowed] or shots
    if avoid:
        banned = set(avoid)
        shots = [s for s in shots if s.index not in banned] or shots
    if not shots:
        return []
    mot = _pct([s.motion for s in shots])
    shr = _pct([s.sharp for s in shots])
    bri = _pct([s.bright for s in shots])
    sat = _pct([s.sat for s in shots])
    out = []
    for i, s in enumerate(shots):
        # brightness is scored for *usable* range, not for being bright: a frame
        # at either end of the scale is a frame the type fights with.
        b = 1.0 - abs(bri[i] - 0.62) * 1.4
        score = 0.44 * mot[i] + 0.26 * shr[i] + 0.18 * max(0.0, b) + 0.12 * sat[i]
        out.append({
            "shot": s.index,
            "in": round(s.src_in, 2),
            "out": round(s.src_out, 2),
            "dur": round(s.dur, 2),
            "score": round(score, 3),
            "motion": round(s.motion, 3),
            "sharp": round(s.sharp, 1),
            "bright": round(s.bright, 1),
            "colour": s.colour,
            "why": ", ".join(filter(None, [
                "moves" if mot[i] > 0.65 else "",
                "sharp" if shr[i] > 0.65 else "",
                "reads under type" if 0.25 < bri[i] < 0.85 else "",
                "saturated" if sat[i] > 0.75 else "",
            ])) or "filler",
        })
    out.sort(key=lambda r: -r["score"])
    return out[:top]


def sheet(src, picks: list[dict], out: str | Path, cols: int = 4,
          tile: tuple[int, int] = (480, 270)) -> Path:
    """The shortlist as a contact sheet: timecode, score and the frame itself."""
    import io
    import subprocess

    from PIL import Image, ImageDraw

    from .shots import ffmpeg

    rows = (len(picks) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tile[0], rows * tile[1]), (10, 10, 12))
    for i, p in enumerate(picks):
        at = (p["in"] + p["out"]) / 2
        proc = subprocess.run(
            [ffmpeg(), "-nostdin", "-ss", f"{at:.2f}", "-i", str(src.path),
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True)
        if not proc.stdout:
            continue
        im = Image.open(io.BytesIO(proc.stdout)).convert("RGB").resize(tile)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, tile[0], 22], fill=(0, 0, 0))
        d.text((6, 5), f"#{p['shot']:02d}  {p['in']:6.2f}s  {p['score']:.2f}  {p['why']}",
               fill=(255, 255, 255))
        canvas.paste(im, ((i % cols) * tile[0], (i // cols) * tile[1]))
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=88)
    return path


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="the moments worth cutting to")
    ap.add_argument("source")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--only", default=None,
                    help="comma separated shot indices that are on subject")
    ap.add_argument("--avoid", default=None,
                    help="comma separated shot indices to leave out")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    src = analyse(a.source, None)

    def ids(v):
        return [int(x) for x in v.split(",")] if v else None

    picks = rank(src, a.top, only=ids(a.only), avoid=ids(a.avoid))
    usable = sum(s.dur for s in src.shots)
    print(f"{src.path}: {len(src.shots)} shots, {usable:.0f}s of picture "
          f"over {src.duration:.0f}s")
    print(f"{'shot':>5} {'in':>8} {'out':>8} {'len':>5} {'score':>6}  why")
    for p in picks:
        print(f"{p['shot']:5d} {p['in']:8.2f} {p['out']:8.2f} {p['dur']:5.2f} "
              f"{p['score']:6.3f}  {p['why']}")
    if a.json:
        Path(a.json).write_text(json.dumps(picks, indent=1) + "\n")
    if a.sheet:
        print(f"sheet: {sheet(src, picks, a.sheet)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
