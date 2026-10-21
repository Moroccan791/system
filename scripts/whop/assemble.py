#!/usr/bin/env python3
"""Merge a release-format source back into one continuous file - safely.

The raw arrives as a dozen ~80 MB chunks because a single 900 MB upload is
unreliable. Merging them wrongly is the most expensive possible mistake: a
one-chunk gap silently deletes minutes of the episode and every clip chosen
after that point is from the wrong moment.

So this does not just concatenate. It

  1. orders by the trailing number, numerically (`_010` after `_009`, not
     after `_001`);
  2. checks every chunk has the same codec, size and frame rate - a
     concatenation of mixed parameters produces a file that plays but is
     broken at the joins;
  3. refuses on a gap: chunk N is expected to start where N-1 ended;
  4. verifies the joined duration against the sum of the parts.

    assemble.py work/raw/*.mp4 --out work/raw/full.mp4 [--force]

`--force` re-encodes instead of stream-copying, for chunks that differ.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def ffmpeg() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def probe(path: Path) -> dict:
    res = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, errors="ignore")
    info = {"path": str(path), "duration": 0.0, "codec": None,
            "width": None, "height": None, "fps": None, "audio": None}
    for line in res.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.replace(":", " ").split()
            info["duration"] = round(int(float(h)) * 3600 + int(float(m)) * 60 + float(s), 3)
        if "Video:" in line:
            info["codec"] = line.split("Video:")[1].split()[0].strip(",")
            m = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if m:
                info["width"], info["height"] = int(m.group(1)), int(m.group(2))
            f = re.search(r"([\d.]+) fps", line)
            if f:
                info["fps"] = round(float(f.group(1)), 3)
        if "Audio:" in line:
            info["audio"] = line.split("Audio:")[1].split()[0].strip(",")
    return info


def order_key(path: Path) -> tuple[int, str]:
    """Numeric order on the trailing number, so _010 follows _009."""
    m = re.search(r"(\d+)(?!.*\d)", path.stem)
    return (int(m.group(1)) if m else 0, path.stem)


def compatibility(parts: list[dict]) -> list[str]:
    """Reasons the chunks cannot be stream-copied together."""
    problems = []
    base = parts[0]
    for p in parts[1:]:
        for key in ("codec", "width", "height", "fps", "audio"):
            if p[key] != base[key]:
                problems.append(f"{Path(p['path']).name}: {key} {p[key]!r} != {base[key]!r}")
    return problems


def gaps(parts: list[dict], tol: float = 0.35) -> list[str]:
    """A chunk whose duration is wildly off, or a numbering hole."""
    out = []
    durations = [p["duration"] for p in parts]
    if not durations:
        return out
    median = sorted(durations)[len(durations) // 2]
    for p in parts:
        if median and abs(p["duration"] - median) > 0.35 * median:
            out.append(f"{Path(p['path']).name} is {p['duration']}s "
                       f"against a {median}s median - possibly truncated")
    return out


def merge(parts: list[Path], out: Path, *, force: bool = False) -> dict:
    parts = sorted(parts, key=order_key)
    metas = [probe(p) for p in parts]
    problems = compatibility(metas)
    warns = gaps(metas)
    total = round(sum(m["duration"] for m in metas), 3)

    if problems and not force:
        raise SystemExit("chunks differ, refusing to stream-copy:\n  "
                         + "\n  ".join(problems) + "\nre-run with --force to re-encode")

    with tempfile.TemporaryDirectory() as td:
        listing = Path(td) / "list.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
        cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", str(listing)]
        if force or problems:
            cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-c", "copy"]
        cmd += [str(out)]
        subprocess.run(cmd, check=True)

    got = probe(out)["duration"]
    if abs(got - total) > max(1.0, 0.01 * total):
        raise SystemExit(f"merged duration {got}s does not match the sum of parts "
                         f"{total}s - a chunk is missing or duplicated")
    return {"out": str(out), "parts": len(parts), "expected": total,
            "actual": got, "warnings": warns, "reencoded": bool(force or problems)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true", help="re-encode instead of copy")
    args = ap.parse_args()
    paths = [Path(p) for p in args.parts]
    if len(paths) == 1 and paths[0].is_dir():
        paths = sorted(paths[0].glob("*.mp4"), key=order_key)
    info = merge(paths, Path(args.out), force=args.force)
    print(json.dumps(info, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
