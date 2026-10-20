#!/usr/bin/env python3
"""Check a raw before anybody spends an evening editing it.

The most expensive mistake in this pipeline is not a bad cut, it is a bad
source: a 480p download that will look soft at 1080, a clip that is clipped
before it starts, a talking head with no face for half its length, or a raw
whose best opening still scores below the hook floor. All of that is knowable
in twenty seconds.

    preflight.py raw.mp4 [--transcript t.json]

Exit code is 1 if anything is FAIL, so it can gate a batch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import director as DIR   # noqa: E402
import hook_lab as HL    # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def probe(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"fps": fps, "frames": frames, "w": w, "h": h,
            "duration": frames / fps if fps else 0.0}


def audio_stats(path: Path) -> dict:
    """Decoded peak/RMS, and how much of the file is pinned at the ceiling."""
    from clipper.ffmpeg import decode_audio
    x = decode_audio(path)
    if not len(x):
        return {"peak_db": None, "rms_db": None, "clipped_pct": None}
    a = np.asarray(x, dtype=np.float32)
    peak = float(np.abs(a).max())
    rms = float(np.sqrt((a.astype(np.float64) ** 2).mean()))
    clipped = float((np.abs(a) > 0.985).mean()) * 100.0
    return {"peak_db": round(20 * np.log10(max(peak, 1e-9)), 1),
            "rms_db": round(20 * np.log10(max(rms, 1e-9)), 1),
            "clipped_pct": round(clipped, 3)}


def check(path: Path, transcript: Path | None = None) -> tuple[list[dict], bool]:
    rows: list[dict] = []
    info = probe(path)
    if not info["frames"]:
        rows.append({"check": "readable", "state": FAIL, "detail": "no video stream"})
        return rows, False
    rows.append({"check": "readable", "state": PASS,
                 "detail": f"{info['w']}x{info['h']}, {info['fps']:.2f} fps, "
                           f"{info['duration']:.1f}s"})

    short = min(info["w"], info["h"])
    state = PASS if short >= 1080 else (WARN if short >= 720 else FAIL)
    rows.append({"check": "resolution", "state": state,
                 "detail": f"short side {short}px"})

    dur = info["duration"]
    state = PASS if 8 <= dur <= 90 else WARN
    rows.append({"check": "length", "state": state, "detail": f"{dur:.1f}s raw"})

    a = audio_stats(path)
    if a["peak_db"] is None:
        rows.append({"check": "audio", "state": FAIL, "detail": "no audio"})
    else:
        clip_state = FAIL if (a["clipped_pct"] or 0) > 0.5 else (
            WARN if (a["clipped_pct"] or 0) > 0.1 else PASS)
        rows.append({"check": "audio", "state": clip_state,
                     "detail": f"peak {a['peak_db']:+.1f} dBFS, "
                               f"{a['clipped_pct']:.2f}% pinned"})

    # face time: how much of the raw is actually a person
    import director as D
    frames = D._sample(path, 0.5)
    face = D.face_stats(frames)
    state = PASS if face["found"] >= 0.7 else (WARN if face["found"] >= 0.4 else FAIL)
    rows.append({"check": "face_time", "state": state,
                 "detail": f"face in {face['found'] * 100:.0f}% of samples, "
                           f"{face['area'] * 100:.0f}% of frame"})

    cuts = D.shot_cuts(frames)
    rows.append({"check": "shots", "state": PASS,
                 "detail": f"{len(cuts) + 1} shot(s)"})

    if transcript and transcript.exists():
        words = HL.read_transcript(transcript, False)
        cands = HL.candidates(words)
        if cands:
            best = cands[0]
            score = float(best.get("score", 0))
            state = PASS if score >= 4.0 else WARN
            rows.append({"check": "hook", "state": state,
                         "detail": f"best opening {score:.1f}/10 - "
                                   f"\"{best.get('spoken', '')[:48]}\""})

    return rows, any(r["state"] == FAIL for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raws", nargs="+")
    ap.add_argument("--transcript", help="transcript json for the hook check")
    args = ap.parse_args()
    failed = False
    for raw in args.raws:
        rows, bad = check(Path(raw), Path(args.transcript) if args.transcript else None)
        failed = failed or bad
        print(f"\nPREFLIGHT — {Path(raw).name}")
        for r in rows:
            print(f"[{r['state']:4s}] {r['check']:11s} {r['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
