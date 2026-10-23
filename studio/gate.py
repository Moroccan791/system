"""The ship gate — what a finished edit must prove before it is uploaded.

Every miss this project has had was a property of the FILE that nobody measured
after the encode: a monophonic mix, a dead black frame on a beat, a handle that
was configured but not on screen, a caption that ran past the music. Each of
those is cheap to check and expensive to notice on a phone, after posting.

The gate renders nothing. It looks at the finished mp4 and answers pass/fail per
property, so "is this ready?" is a command and not a mood:

    python -m studio.gate studio/out/tom_holland_v8.mp4 --script studio/out/tom_holland_v8.script.json

It is run at the end of `studio.pipeline` for the same reason the sync check is:
a take that fails the gate does not ship, and the failure is printed where the
work happened rather than discovered during the upload.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


# The frame is 1920x1080 at this studio's only aspect. Vertical was dropped, so
# anything else here is a mistake rather than a platform choice.
from . import frame as _frame  # noqa: E402


def _want() -> tuple[int, int]:
    return _frame.size()


WANT_W, WANT_H = 1920, 1080
WANT_FPS = 30.0
BLACK = 12.0          # a frame this dark has no picture in it
HANDLE_DELTA = 8.0    # how much brighter the handle must sit than its surround


def probe(path: str | Path) -> dict:
    """Stream facts from ffmpeg's banner. No decode."""
    out = subprocess.run([ffmpeg(), "-nostdin", "-i", str(path)],
                         capture_output=True, text=True).stderr
    info = {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0,
            "audio": None, "acodec": ""}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            info["duration"] = int(h) * 3600 + int(m) * 60 + float(s)
        elif "Video:" in line:
            hit = re.search(r"(?<![\d.])(\d{2,5})x(\d{2,5})(?![\d.])", line)
            if hit:
                info["width"], info["height"] = int(hit.group(1)), int(hit.group(2))
            fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
            if fps:
                info["fps"] = float(fps.group(1))
        elif "Audio:" in line:
            low = line.lower()
            info["acodec"] = "aac" if "aac" in low else "other"
            info["audio"] = 2 if "stereo" in low else (1 if "mono" in low else None)
    return info


def _decode(path: str | Path, vf: str) -> bytes:
    return subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-i", str(path), "-vf", vf,
         "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout


def _grey_frames(path: str | Path, w: int = 320, h: int = 180,
                 fps: float = 2.0) -> np.ndarray:
    """A coarse greyscale decode — enough to measure, cheap enough to run."""
    raw = _decode(path, f"fps={fps},scale={w}:{h}")
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)


def handle_delta(path: str | Path, box: tuple[int, int, int, int],
                 mask: np.ndarray, fps: float = 3.0) -> tuple[float, int]:
    """How much brighter the handle's own glyph box is than the pixels beside it.

    The box comes from the compositor's own geometry, so this asks the only
    question worth asking: are the configured glyphs actually in the frame? A
    handle that was configured and never composited reads ~0 here, and a correct
    one reads tens of levels — measured on this pack, +70 against -0.2.
    """
    x, y, w, h = box
    raw = _decode(path, f"fps={fps},crop={w}:{h}:{x}:{y}")
    n = len(raw) // (w * h)
    if n == 0:
        return 0.0, 0
    a = np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)
    delta = a[:, mask].mean(axis=1) - a[:, ~mask].mean(axis=1)
    return float(np.median(delta)), int(n)


def run(path: str | Path, script: str | Path | None = None,
        want_handle: bool = True) -> dict:
    """Every check, as data. `ok` is the AND of the blocking ones."""
    global WANT_W, WANT_H
    WANT_W, WANT_H = _want()
    p = Path(path)
    info = probe(p)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, blocking: bool = True) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail,
                       "blocking": blocking})

    check("resolution", (info["width"], info["height"]) == (WANT_W, WANT_H),
          f"{info['width']}x{info['height']}")
    check("frame rate", abs(info["fps"] - WANT_FPS) < 0.05, f"{info['fps']:.2f} fps")
    check("audio", info["audio"] == 2, f"{info['audio']} channel(s)")

    frames = _grey_frames(p)
    if len(frames) == 0:
        check("picture", False, "no frames decoded")
    else:
        dark = int((frames.mean(axis=(1, 2)) < BLACK).sum())
        check("no dead frames", dark == 0, f"{dark} frame(s) below luma {BLACK:.0f}")

        if want_handle:
            from . import watermark

            st = watermark.settings()
            tile = watermark._overlay(WANT_W, WANT_H, st) if st["text"] else None
            if tile is None:
                check("handle", False, "no handle configured in family.json")
            else:
                tw, th = tile.size
                mask = np.asarray(tile)[..., 3] > 40
                rect = watermark.rect_from_video(p, WANT_W, WANT_H)
                ok_x, ok_y = watermark.home(WANT_W, WANT_H, tw, th, rect)
                delta, n = handle_delta(p, (ok_x, ok_y, tw, th), mask)
                where = "on the picture"
                if delta < HANDLE_DELTA:
                    # Files rendered before this rule had the handle a margin
                    # from the FRAME's bottom edge, which on a letterboxed pack
                    # is inside the black band. The check is whether the mark is
                    # there, not whether it matches today's code — but it says
                    # which, so an old file is caught rather than quietly passing.
                    legacy = (int(round((WANT_W - tw) / 2)),
                              WANT_H - int(round(WANT_H * 0.055)) - th, tw, th)
                    d2, n2 = handle_delta(p, legacy, mask)
                    if d2 >= HANDLE_DELTA:
                        delta, n, where = d2, n2, "in the letterbox (legacy placement)"
                check("handle", delta >= HANDLE_DELTA and n > 0,
                      f"brightness +{delta:.0f} over its surround ({n} frames), {where}")

    if script:
        sc = json.loads(Path(script).read_text())
        cards = sc.get("cards", [])
        bpm = float(sc.get("bpm", 120.0))
        if cards:
            last = max(float(c.get("until", c.get("beat", 0))) for c in cards)
            last_s = last * 60.0 / bpm
            check("captions fit", last_s - info["duration"] <= 0.10,
                  f"last card {last_s:.2f}s vs {info['duration']:.2f}s of picture")

    ok = all(c["ok"] for c in checks if c["blocking"])
    return {"file": str(p), "ok": ok, "checks": checks, "info": info}


def report(result: dict) -> str:
    lines = [f"ship gate — {Path(result['file']).name}"]
    for c in result["checks"]:
        lines.append(f"  {'PASS' if c['ok'] else 'FAIL'}  {c['name']:<16} {c['detail']}")
    lines.append(f"  {'READY TO POST' if result['ok'] else 'DO NOT POST'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="check a finished edit before upload")
    ap.add_argument("video")
    ap.add_argument("--script", default=None, help="the card script, to check the outro")
    ap.add_argument("--no-handle", action="store_true",
                    help="skip the watermark check (a video for someone else)")
    ap.add_argument("--out", default=None, help="write the report here")
    a = ap.parse_args(argv)
    res = run(a.video, a.script, want_handle=not a.no_handle)
    text = report(res)
    print(text)
    target = Path(a.out) if a.out else Path(a.video).with_suffix(".gate.txt")
    target.write_text(text + "\n")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
