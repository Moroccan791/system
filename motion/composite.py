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


# Named cinematic grades (the refs' baseline table stakes: mixed
# locations unified under one look, not our neutral denoise/sharpen).
# "subject_pop" grades globally like brand; its selective half
# (background dimmed+desaturated behind the matte) is built in
# composite() where the person mask is available.
GRADE_PRESETS = {
    "teal": ("eq=contrast=1.12:saturation=1.14,"
             "colorbalance=rs=-0.07:gs=0.03:bs=0.10:"
             "rm=0.00:gm=0.02:bm=0.02:rh=0.05:gh=0.02:bh=-0.03"),
    "warm": ("eq=contrast=1.09:saturation=1.16,"
             "colorbalance=rs=0.09:gs=0.03:bs=-0.08:"
             "rm=0.04:gm=0.01:bm=-0.03:rh=0.03:gh=0.01:bh=-0.02"),
    "punchy": "eq=contrast=1.18:saturation=1.26",
}


def grade_filter(name: str | None, accent: str) -> str:
    if not name or name in ("brand", "subject_pop"):
        return _grade(accent)
    if name not in GRADE_PRESETS:
        raise ValueError(f"unknown grade {name!r} "
                         f"(brand, teal, warm, punchy, subject_pop)")
    return GRADE_PRESETS[name]


# the selective half of subject_pop: the room goes quiet, the
# speaker keeps the brand grade (R1's dark-office look)
POP_BG_FILTER = "eq=saturation=0.52:brightness=-0.075:contrast=1.03"


def normalize_png_alpha(frames: Path) -> int:
    """Normalize every rendered frame to RGBA before FFmpeg sees the sequence.

    Chromium omits the alpha channel on frames that happen to be fully
    opaque (notably the first hard-in frame of an end card), while earlier
    frames in the same sequence are RGBA. FFmpeg's image2 input can retain
    the prior partial alpha when that pixel format changes, making the
    supposedly opaque slate translucent over the speaker. An explicit 255
    alpha channel on RGB frames keeps the frame sequence format stable.
    """
    from PIL import Image

    converted = 0
    for path in sorted(frames.glob("*.png")):
        with Image.open(path) as im:
            if im.mode == "RGBA":
                continue
            rgba = im.convert("RGBA")
            rgba.save(path, format="PNG", compress_level=1)
            converted += 1
    if converted:
        print(f"normalized {converted} opaque RGB frames to RGBA")
    return converted


def composite(base: Path, frames: Path, tl: dict, out: Path,
              behind_frames: Path | None = None,
              mask: Path | None = None,
              grade: str | None = None) -> Path:
    normalize_png_alpha(frames)
    fps = int(tl.get("fps") or 30)
    accent = (tl.get("brand") or {}).get("accent") or "#FFC531"
    items = tl.get("items") or []
    opening = any(i.get("type") == "fx" and i.get("kind") == "opening" for i in items)
    bw = [i for i in items if i.get("type") == "fx" and i.get("kind") == "bwflash"]

    chains = [f"[0:v]{grade_filter(grade, accent)}[g]"]
    src = "[g]"
    if grade == "subject_pop":
        if mask is None:
            raise ValueError("grade subject_pop needs a person mask "
                             "(motion/matte.py) - refusing to fake it")
        mi = 3 if behind_frames is not None else 2
        chains += [
            f"{src}split=2[popbg][popfg]",
            f"[popbg]{POP_BG_FILTER}[popbgq]",
            f"[{mi}:v]fps={fps}[popmask]",
            "[popfg][popmask]alphamerge,format=yuva444p[popper]",
            "[popbgq][popper]overlay=0:0:format=auto:eof_action=pass[popout]",
        ]
        src = "[popout]"
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
    # emphasis punch-ins: a hard cut to a <=1.05x tighter shot for a
    # blink (0.25-0.6s) on a payoff word - the standard punch, done as
    # stepped overlays on ONE stream (never split/trim/concat)
    punches = [i for i in items if i.get("type") == "fx"
               and i.get("kind") == "punch"][:3]
    for j, it in enumerate(punches):
        a = float(it["at"]); d = float(it.get("dur") or 0.35)
        z = float(it.get("zoom") or 1.05)
        sw, sh = int(1080 * z) // 2 * 2, int(1920 * z) // 2 * 2
        chains += [
            f"{src}split=2[pbase{j}][pzoom{j}]",
            f"[pzoom{j}]scale={sw}:{sh},"
            f"crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2[pz{j}]",
            f"[pbase{j}][pz{j}]overlay=0:0:"
            f"enable='between(t,{a:.3f},{a + d:.3f})'[pout{j}]",
        ]
        src = f"[pout{j}]"
    # freeze-frame holds: the exact frame at `at`, slightly pushed
    # and saturated, held 0.3-1.0s while graphics land on it. Built
    # as still-image inputs (watermark-style overlay) - an in-graph
    # trim/loop clone stalls the overlay framesync and silently
    # truncates the stream (measured: 380 of 420 frames out)
    freezes = [i for i in items if i.get("type") == "fx"
               and i.get("kind") == "freeze"][:2]
    freeze_stills: list[Path] = []
    still0 = 2 + (2 if (behind_frames is not None and mask is not None)
                  else (1 if mask is not None else 0))
    for j, it in enumerate(freezes):
        a = float(it["at"]); d = float(it.get("dur") or 0.5)
        still = out.parent / f".freeze{j}.png"
        _run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(base),
              "-ss", f"{a:.3f}", "-frames:v", "1", str(still)])
        freeze_stills.append(still)
        chains += [
            f"[{still0 + j}:v]{_grade(accent)},scale=1148:2040,"
            f"crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,"
            f"eq=saturation=1.08,format=yuv420p[ff{j}]",
            f"{src}[ff{j}]overlay=0:0:"
            f"enable='between(t,{a:.3f},{a + d:.3f})'[fout{j}]",
        ]
        src = f"[fout{j}]"
    if behind_frames is not None and mask is not None:
        # behind-the-person stack: the same graded stream splits - one
        # copy takes the behind-graphics, the other is re-alpha'd with
        # the person matte and laid back over them, so authorised words
        # sit physically behind the speaker (matte.py makes the mask;
        # grade parity is automatic, both copies share the grade)
        chains += [
            f"{src}split=2[bgb][fgp]",
            "[bgb][2:v]overlay=0:0:format=auto:eof_action=pass[withb]",
            f"[3:v]fps={fps}[maskf]",
            "[fgp][maskf]alphamerge,format=yuva444p[person]",
            "[withb][person]overlay=0:0:format=auto:eof_action=pass[srcb]",
        ]
        src = "[srcb]"
    chains.append(f"{src}[1:v]overlay=0:0:format=auto:eof_action=pass,fps={fps}[vout]")

    # audio: whoosh on card/chip/fx transitions, pop on chips
    sfx: list[tuple[float, Path, float]] = []
    for it in items:
        at = float(it.get("at") or 0)
        if at <= 0.05:
            continue
        if it["type"] in ("card", "chip", "fx", "pip", "broll", "counter",
                          "list", "process"):
            sfx.append((at, WHOOSH, 0.30))
        if it["type"] == "chip":
            sfx.append((at, POP, 0.25))
        if it["type"] == "counter":   # soft pop the frame the count lands
            sfx.append((at + float(it.get("countDur") or 0.9), POP, 0.22))
        for key in ("items", "steps"):   # a pop per plate / step as it lands
            for sub in it.get(key) or []:
                sfx.append((float(sub["at"]), POP, 0.18))
    info = probe(base)
    fc = ";".join(chains)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Pass 1: video only. (The old one-pass A/V encode silently ate the
    # audio tail -- with the PNG-sequence input in the same graph,
    # ffmpeg ended the mixed audio up to ~0.7s early, and the sound
    # stage's -shortest then cut the picture to match, chopping clip
    # endings. Two passes keep both streams full-length.)
    vid = out.with_suffix(".vid.mp4")
    args = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(base),
            "-framerate", str(fps), "-i", str(frames / "%05d.png")]
    if behind_frames is not None and mask is not None:
        args += ["-framerate", str(fps), "-i", str(behind_frames / "%05d.png"),
                 "-i", str(mask)]
    elif mask is not None:
        args += ["-i", str(mask)]
    for still in freeze_stills:
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(still)]
    args += ["-filter_complex", fc, "-map", "[vout]"]
    if tl.get("duration"):
        args += ["-t", f"{float(tl['duration']):.3f}"]
    # VBV cap on the CRF: with the grain treatment adopted (2026-10-16),
    # uncapped crf17 spends ~30 Mbps preserving noise and a 35s clip
    # balloons past 100 MB. Platforms re-encode to ~10 Mbps anyway, so
    # 10M/20M keeps the visible quality and bounds delivery size.
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
             "-maxrate", "10M", "-bufsize", "20M",
             "-pix_fmt", "yuv420p", "-an", str(vid)]
    _run(args)
    for still in freeze_stills:
        still.unlink(missing_ok=True)
    # Pass 2: audio (base voice + transition SFX) muxed onto the video.
    args = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(vid),
            "-i", str(base)]
    if sfx and info.has_audio:
        parts = ["[1:a]anull[abase]"]
        labels = ["[abase]"]
        for j, (at, f, vol) in enumerate(sfx):
            ms = int(at * 1000)
            parts.append(f"[{2 + j}:a]adelay={ms}|{ms},volume={vol}[s{j}]")
            labels.append(f"[s{j}]")
        parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:"
                     "dropout_transition=0:normalize=0[aout]")
        for _, f, _ in sfx:
            args += ["-i", str(f)]
        args += ["-filter_complex", ";".join(parts),
                 "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "160k"]
    elif info.has_audio:
        args += ["-map", "0:v", "-map", "1:a", "-c", "copy"]
    else:
        args += ["-map", "0:v", "-c", "copy"]
    if tl.get("duration"):
        args += ["-t", f"{float(tl['duration']):.3f}"]
    args += ["-movflags", "+faststart", str(out)]
    _run(args)
    vid.unlink()
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
        argv = sys.argv[1:]
        behind = mask = None
        grade = None
        if "--grade" in argv:
            grade = argv[argv.index("--grade") + 1]
            argv = [a for a in argv if a not in ("--grade", grade)]
        if "--behind" in argv:
            behind = Path(argv[argv.index("--behind") + 1])
            mask = Path(argv[argv.index("--mask") + 1])
            argv = [a for a in argv if a not in ("--behind", "--mask")
                    and a not in (str(behind), str(mask))]
        elif "--mask" in argv:
            mask = Path(argv[argv.index("--mask") + 1])
            argv = [a for a in argv if a not in ("--mask", str(mask))]
        base, frames, tl_path, out = (Path(argv[0]), Path(argv[1]),
                                      Path(argv[2]), Path(argv[3]))
        composite(base, frames, json.loads(tl_path.read_text()), out,
                  behind_frames=behind, mask=mask, grade=grade)
        side = Path(str(tl_path) + ".transitions.json")
        if side.exists():   # cut/transition sidecar travels with the video
            dest = out.with_name(out.stem + ".transitions.json")
            dest.write_text(side.read_text())
            print(dest)
        print(out)
