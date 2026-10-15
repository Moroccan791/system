#!/usr/bin/env python3
"""Composite rendered motion-graphics frames over a base video.

    python motion/composite.py <base.mp4> <framesDir> <timeline.json> <out.mp4>
    python motion/composite.py --sheet <video> <timeline.json> <outPrefix>

Video path: mild palette grade toward the brand accent -> opening
blur-to-sharp zoom (first 8 frames, if an "opening" fx is in the
timeline) -> black-and-white flashes (fx kind "bwflash") -> PNG-frame
overlay. Audio: the base track plus a whoosh on every card/chip/fx
transition and a pop on every chip (amix normalize=0, voice untouched).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from clipper.ffmpeg import ffmpeg_exe, probe  # noqa: E402

WHOOSH = ROOT / "assets" / "sfx" / "whoosh.wav"
POP = ROOT / "assets" / "sfx" / "pop.wav"


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{proc.stderr[-2000:]}")


def _grade(accent: str) -> str:
    r, g, b = (int(accent[i:i + 2], 16) / 255 for i in (1, 3, 5))
    # mild contrast/saturation plus a whisper of the accent in the shadows
    return (f"eq=contrast=1.06:saturation=1.05,"
            f"colorbalance=rs={0.05 * (r - .5):.3f}:gs={0.05 * (g - .5):.3f}:"
            f"bs={0.05 * (b - .5):.3f}")


def composite(base: Path, frames: Path, tl: dict, out: Path) -> Path:
    fps = int(tl.get("fps") or 30)
    accent = (tl.get("brand") or {}).get("accent") or "#FFC531"
    items = tl.get("items") or []
    opening = any(i.get("type") == "fx" and i.get("kind") == "opening" for i in items)
    bw = [i for i in items if i.get("type") == "fx" and i.get("kind") == "bwflash"]

    chains = [f"[0:v]{_grade(accent)}[g]"]
    src = "[g]"
    for i, it in enumerate(bw):
        a = float(it["at"]); d = float(it.get("dur") or 0.12)
        chains.append(f"{src}hue=s=0:enable='between(t,{a:.3f},{a + d:.3f})'[bw{i}]")
        src = f"[bw{i}]"
    if opening:
        # stepped blur-zoom over the first 8 frames via overlay enable
        # windows on ONE continuous stream — never split/trim/concat:
        # concat's timestamp handling silently truncates the video.
        f1, f2 = 4 / fps, 8 / fps
        chains += [
            f"{src}split=3[sharp][zb1][zb2]",
            "[zb1]trim=duration=0.3,setpts=PTS-STARTPTS,scale=1188:2112,"
            "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,gblur=sigma=8[z1]",
            "[zb2]trim=duration=0.3,setpts=PTS-STARTPTS,scale=1134:2016,"
            "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,gblur=sigma=3[z2]",
            f"[sharp][z1]overlay=0:0:enable='lt(t,{f1:.4f})'[o1]",
            f"[o1][z2]overlay=0:0:enable='between(t,{f1:.4f},{f2:.4f})'[opened]",
        ]
        src = "[opened]"
    chains.append(f"{src}[1:v]overlay=0:0:format=auto:eof_action=pass,fps={fps}[vout]")

    # audio: whoosh on card/chip/fx transitions, pop on chips
    sfx: list[tuple[float, Path, float]] = []
    for it in items:
        at = float(it.get("at") or 0)
        if at <= 0.05:
            continue
        if it["type"] in ("card", "chip", "fx"):
            sfx.append((at, WHOOSH, 0.30))
        if it["type"] == "chip":
            sfx.append((at, POP, 0.25))
    info = probe(base)

    args = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(base),
            "-framerate", str(fps), "-i", str(frames / "%05d.png")]
    fc = ";".join(chains)
    if sfx and info.has_audio:
        parts = ["[0:a]anull[abase]"]
        labels = ["[abase]"]
        for j, (at, f, vol) in enumerate(sfx):
            ms = int(at * 1000)
            parts.append(f"[{2 + j}:a]adelay={ms}|{ms},volume={vol}[s{j}]")
            labels.append(f"[s{j}]")
        parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:"
                     "dropout_transition=0:normalize=0[aout]")
        for _, f, _ in sfx:
            args += ["-i", str(f)]
        args += ["-filter_complex", ";".join([fc] + parts),
                 "-map", "[vout]", "-map", "[aout]"]
    else:
        args += ["-filter_complex", fc, "-map", "[vout]"]
        if info.has_audio:
            args += ["-map", "0:a"]
    if tl.get("duration"):
        args += ["-t", f"{float(tl['duration']):.3f}"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(args)
    return out


def contact_sheet(video: Path, tl: dict, prefix: Path) -> list[Path]:
    dur = float(tl.get("duration") or probe(video).duration or 10)
    cols = 5
    rows = max(1, int(dur * 2) // cols + 1)
    sheet = Path(f"{prefix}_sheet.jpg")
    _run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(video),
          "-vf", f"fps=2,scale=270:480,tile={cols}x{rows}", "-frames:v", "1", "-update", "1",
          "-q:v", "3", str(sheet)])
    outs = [sheet]
    fps = int(tl.get("fps") or 30)
    transitions = sorted({round(float(i["at"]), 2) for i in tl.get("items") or []
                          if float(i.get("at") or 0) > 0.4})
    for t in transitions:
        strip = Path(f"{prefix}_strip_{t:.2f}.jpg")
        # frame-number select: -ss (either side) silently drifts on
        # these encodes and the strip shows the wrong moment
        f0 = max(0, round(t * fps) - 2)
        _run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(video),
              "-vf", f"select='between(n\\,{f0}\\,{f0 + 4})',scale=270:480,tile=5x1",
              "-vsync", "0", "-frames:v", "1", "-update", "1", "-q:v", "3", str(strip)])
        outs.append(strip)
    return outs


if __name__ == "__main__":
    if sys.argv[1] == "--sheet":
        video, tl_path, prefix = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
        for p in contact_sheet(video, json.loads(tl_path.read_text()), prefix):
            print(p)
    else:
        base, frames, tl_path, out = (Path(sys.argv[1]), Path(sys.argv[2]),
                                      Path(sys.argv[3]), Path(sys.argv[4]))
        composite(base, frames, json.loads(tl_path.read_text()), out)
        print(out)
