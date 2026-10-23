"""Two songs, one edit: the bed that makes "quiet then metal" possible.

The formats that change an edit's temperature work because the MUSIC changes, not
because the picture does — twenty seconds of something gentle, a hard cut, then
the drop. That is a mix, not a renderer feature, so what this module builds is a
single track: song A to the join, song B from the join, one file out, plus the
join time so the direction sheet can put its turn there.

The cut at the join is exactly that — a cut. Crossfading it would defeat the
point; the format lives on the seam being violent.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def build(a: str | Path, b: str | Path, out: str | Path,
          a_secs: float, b_secs: float, b_from: float = 0.0,
          loudness: bool = True) -> dict:
    """A[0:a_secs] + B[b_from:b_from+b_secs] -> one stereo wav."""
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".raw.wav")
    fc = (f"[0:a]atrim=0:{a_secs:.3f},asetpts=N/SR/TB,"
          f"aformat=sample_rates=48000:channel_layouts=stereo[s0];"
          f"[1:a]atrim={b_from:.3f}:{b_from + b_secs:.3f},asetpts=N/SR/TB,"
          f"aformat=sample_rates=48000:channel_layouts=stereo[s1];"
          f"[s0][s1]concat=n=2:v=0:a=1[out]")
    subprocess.run([ff, "-nostdin", "-v", "error", "-y",
                    "-i", str(a), "-i", str(b),
                    "-filter_complex", fc, "-map", "[out]", str(tmp)], check=True)

    if loudness:
        # one loudness pass over the whole bed: the two songs come from different
        # masters and the join would otherwise be a 6dB step, which reads as a
        # mistake rather than a turn.
        subprocess.run([ff, "-nostdin", "-v", "error", "-y", "-i", str(tmp),
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar", "48000", str(out)], check=True)
        tmp.unlink(missing_ok=True)
    else:
        tmp.replace(out)

    return {"track": str(out), "join": round(a_secs, 3),
            "duration": round(a_secs + b_secs, 3),
            "a": str(a), "b": str(b), "b_from": round(b_from, 3)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="build a two-song bed")
    ap.add_argument("--a", required=True, help="the quiet song")
    ap.add_argument("--b", required=True, help="the one it turns into")
    ap.add_argument("--out", required=True)
    ap.add_argument("--a-secs", type=float, required=True)
    ap.add_argument("--b-secs", type=float, required=True)
    ap.add_argument("--b-from", type=float, default=0.0)
    ap.add_argument("--no-loudness", action="store_true")
    a = ap.parse_args(argv)
    info = build(a.a, a.b, a.out, a.a_secs, a.b_secs, a.b_from,
                 loudness=not a.no_loudness)
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
