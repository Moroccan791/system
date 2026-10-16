"""Automated post-render QC (House rule: every render gets checked).

Checks, each reported pass / warn / fail with a one-line detail:

  first_caption      first caption block appears within 1 s of the start
  caption_face       no caption box overlaps a detected face
  static_shot        no run of frozen background longer than 4 s
  loudness           integrated loudness inside the platform window
  hook_match         headline words match what is said in the first 2 s
                     (and the first spoken word is not a throwaway lead-in)
  duration           clip length inside the 25-40 s default window
  logo_scan          heuristic scan for a persistent corner graphic that
                     could be another platform's watermark (warn only -
                     designed marks like our own handle must be eyeballed)

`run_qc` never raises for a bad video: a broken probe is a failed check.
The pipeline runs it after every render and saves <video>.qc.json beside
the output; `clipper qc VIDEO [--ass X] [--transcript X] [--start S]`
runs it standalone.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .ffmpeg import iter_frames, loudness, probe
from .util import log

LEAD_INS = {"so", "no", "okay", "ok", "well", "you", "see", "and", "but",
            "yeah", "right", "like", "um", "uh", "now"}

_STOP = {"the", "a", "an", "to", "of", "and", "or", "is", "it", "in", "on",
         "you", "i", "that", "this", "for", "with", "are", "was", "be"}


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


# ---------------------------------------------------------------- ASS parse

_TAG = re.compile(r"\{[^}]*\}")
_POS = re.compile(r"\\pos\(([-\d.]+),([-\d.]+)\)")
_FS = re.compile(r"\\fs([\d.]+)")


def _ts(text: str) -> float:
    h, m, s = text.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_ass_events(path: str | Path) -> list[dict]:
    """Dialogue events: style, start/end (s), clean text, \\pos and \\fs."""
    events: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        body = parts[9]
        pos = _POS.search(body)
        fs = _FS.search(body)
        events.append({
            "style": parts[3].strip(),
            "start": _ts(parts[1]), "end": _ts(parts[2]),
            "text": _TAG.sub("", body).replace("\\N", " ").strip(),
            "pos": (float(pos.group(1)), float(pos.group(2))) if pos else None,
            "fs": float(fs.group(1)) if fs else None,
        })
    return events


# ------------------------------------------------------------------- checks

def check_first_caption(events: list[dict]) -> dict:
    blocks = [e for e in events if e["style"] in ("Block", "Poster")]
    if not blocks:
        return _check("first_caption", "warn", "no caption events in the ASS")
    first = min(e["start"] for e in blocks)
    ok = first <= 1.0
    return _check("first_caption", "pass" if ok else "fail",
                  f"first caption at {first:.2f} s (limit 1.00 s)")


def check_caption_face(video: Path, events: list[dict]) -> dict:
    blocks = [e for e in events if e["style"] in ("Block", "Poster") and e["pos"]]
    if not blocks:
        return _check("caption_face", "warn", "no positioned caption events to check")
    try:
        import cv2
    except ImportError:
        return _check("caption_face", "warn", "opencv not available")
    from .captions.block import _text_width
    from .edit.reframe import _MODEL, _detector

    if not _MODEL.exists():
        return _check("caption_face", "warn", "YuNet model missing")
    det = _detector()
    if det is None:
        return _check("caption_face", "warn", "YuNet detector unavailable")
    info = probe(video)
    scale = (info.height or 1920) / 1920.0
    hits: list[str] = []
    seen: set[float] = set()
    for e in blocks:
        t = round(e["start"] + 0.05, 2)
        if t in seen:
            continue
        seen.add(t)
        if len(seen) > 40:
            break
        frame = next(iter_frames(video, size=(540, 960), start=t, duration=0.1),
                     None)
        if frame is None:
            continue
        det.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = det.detect(frame)
        if faces is None or not len(faces):
            continue
        fx = frame.shape[1] / float(info.width or 1080)
        fy = frame.shape[0] / float(info.height or 1920)
        x, y = e["pos"]
        fs = e["fs"] or 84 * scale
        w = _text_width(e["text"], fs) * fx
        if e["style"] == "Poster":
            # \an5: pos is the centre of the stack row
            box = (x * fx - w / 2, y * fy - fs * 0.6 * fy,
                   x * fx + w / 2, y * fy + fs * 0.6 * fy)
        else:
            # Block events anchor top-left (\an7): box = pos .. pos+size
            box = (x * fx, y * fy, x * fx + w, y * fy + fs * 1.22 * fy)
        for f in faces:
            fx0, fy0, fw, fh = (float(f[0]), float(f[1]),
                                float(f[2]), float(f[3]))
            ix = max(0.0, min(box[2], fx0 + fw) - max(box[0], fx0))
            iy = max(0.0, min(box[3], fy0 + fh) - max(box[1], fy0))
            if ix * iy > 0.05 * fw * fh:
                hits.append(f"{t:.1f} s")
                break
    if hits:
        return _check("caption_face", "fail",
                      f"caption overlaps a face at {', '.join(hits[:4])}"
                      + (" ..." if len(hits) > 4 else ""))
    return _check("caption_face", "pass",
                  f"no overlap in {len(seen)} sampled caption moments")


def check_static_shot(video: Path, *, threshold_s: float = 4.0) -> dict:
    """Longest run of near-identical background (corner patches) at 5 fps.

    Corners, not the whole frame: the speaker keeps moving inside a static
    SHOT, but a locked-off camera's background does not - and a face close
    to a corner still only covers one patch of four.
    """
    prev = None
    run = longest = 0.0
    step = 0.2
    patches = None
    try:
        for frame in iter_frames(video, size=(160, 284), fps=5, pix_fmt="gray"):
            g = frame.astype("float32")
            if patches is None:
                h, w = g.shape
                patches = [(0, 0), (w - 40, 0), (0, h - 40), (w - 40, h - 40)]
            if prev is not None:
                mad = max(float(abs(g[y:y + 40, x:x + 40]
                                    - prev[y:y + 40, x:x + 40]).mean())
                          for x, y in patches)
                run = run + step if mad < 0.8 else 0.0
                longest = max(longest, run)
            prev = g
    except Exception as exc:
        return _check("static_shot", "warn", f"frame scan failed ({exc})")
    ok = longest <= threshold_s
    return _check("static_shot", "pass" if ok else "fail",
                  f"longest frozen background {longest:.1f} s (limit {threshold_s:.0f} s)")


def check_loudness(video: Path) -> dict:
    data = loudness(video)
    lufs = data.get("integrated_lufs")
    if lufs is None:
        return _check("loudness", "warn", "could not measure integrated loudness")
    ok = -23.0 <= lufs <= -11.0
    return _check("loudness", "pass" if ok else "fail",
                  f"{lufs:.1f} LUFS integrated (window -23..-11)")


def check_hook(hook_lines: list[str] | None, words: list[dict]) -> dict:
    if not words:
        return _check("hook_match", "warn", "no transcript words supplied")
    first_word = re.sub(r"[^a-z']", "", str(words[0].get("text", "")).lower())
    notes = []
    if first_word in LEAD_INS:
        notes.append(f"opens with lead-in '{first_word}'")
    status = "pass"
    if hook_lines:
        def stems(ws: list[str]) -> set[str]:
            out = set()
            for w in ws:
                w = re.sub(r"[^a-z0-9']", "", w.lower()).rstrip("'s")
                if w in _STOP or not w:
                    continue
                stem = re.sub(r"(ing|ed|es|s)$", "", w)
                out |= {stem, w[:5]}  # graded/grade meet at the prefix
            return out

        headline = stems(" ".join(hook_lines).split())
        spoken = stems([str(w.get("text", "")) for w in words
                        if float(w.get("start") or 0) <= 2.0])
        overlap = (len(headline & spoken) / len(headline)) if headline else 0.0
        notes.append(f"headline/first-2 s word overlap {overlap:.0%}")
        if overlap < 0.4:
            status = "fail"
    if notes and status == "pass" and first_word in LEAD_INS:
        status = "warn"
    return _check("hook_match", status, "; ".join(notes) or "ok")


def check_duration(video: Path) -> dict:
    d = float(probe(video).duration or 0)
    ok = 25.0 <= d <= 40.0
    return _check("duration", "pass" if ok else "warn",
                  f"{d:.1f} s (default window 25-40 s; story may overrule)")


def check_logo_scan(video: Path) -> dict:
    """Median-frame corner heuristic for a burned-in platform watermark.

    A watermark survives a time-median; scene content mostly does not.
    Warn-level only: our own handle/watermark are corner graphics too, so
    a human confirms. Bottom-right is skipped (the handle lives there).
    """
    try:
        import numpy as np
    except ImportError:
        return _check("logo_scan", "warn", "numpy not available")
    frames = []
    try:
        for frame in iter_frames(video, size=(270, 480), fps=1, pix_fmt="gray"):
            frames.append(frame.astype("float32"))
            if len(frames) >= 15:
                break
    except Exception as exc:
        return _check("logo_scan", "warn", f"frame scan failed ({exc})")
    if len(frames) < 5:
        return _check("logo_scan", "warn", "too few frames to scan")
    med = np.median(np.stack(frames), axis=0)
    h, w = med.shape
    corners = {
        "top-left": med[: int(h * 0.10), : int(w * 0.30)],
        "top-right": med[: int(h * 0.10), int(w * 0.70):],
        "bottom-left": med[int(h * 0.90):, : int(w * 0.30)],
    }
    busy = []
    for name, region in corners.items():
        edges = float((abs(np.diff(region, axis=1)) > 24).mean())
        if edges > 0.10:
            busy.append(f"{name} ({edges:.0%} edges)")
    if busy:
        return _check("logo_scan", "warn",
                      "persistent corner graphic at " + ", ".join(busy)
                      + " - confirm it is ours, not another platform's mark")
    return _check("logo_scan", "pass", "no persistent corner graphic detected")


def check_visual_pacing(events: list[dict]) -> dict:
    """The next-level rule: a visual event at least every ~3.5 s.

    Caption blocks, poster stacks, claim cards and sticker changes all
    count; a longer stretch means the frame sat still while someone was
    talking - exactly what the reference format never allows.
    """
    starts = sorted(e["start"] for e in events
                    if e["style"] in ("Block", "Poster", "Card"))
    if len(starts) < 2:
        return _check("visual_pacing", "warn", "too few visual events to judge")
    gaps = [(b - a, a) for a, b in zip(starts, starts[1:])]
    worst, at = max(gaps)
    ok = worst <= 3.5
    return _check("visual_pacing", "pass" if ok else "fail",
                  f"longest stretch without a visual event {worst:.1f} s "
                  f"at {at:.1f} s (limit 3.5 s)")


# -------------------------------------------------------------------- entry

def run_qc(video: str | Path, *, ass: str | Path | None = None,
           hook_lines: list[str] | None = None,
           words: list[dict] | None = None) -> dict:
    video = Path(video)
    checks: list[dict] = []
    events: list[dict] = []
    if ass and Path(ass).exists():
        events = parse_ass_events(ass)
        checks.append(check_first_caption(events))
        checks.append(check_caption_face(video, events))
    else:
        checks.append(_check("first_caption", "warn", "no ASS supplied"))
        checks.append(_check("caption_face", "warn", "no ASS supplied"))
    checks.append(check_static_shot(video))
    checks.append(check_visual_pacing(events))
    checks.append(check_loudness(video))
    checks.append(check_hook(hook_lines, words or []))
    checks.append(check_duration(video))
    checks.append(check_logo_scan(video))
    ok = all(c["status"] != "fail" for c in checks)
    return {"video": str(video), "ok": ok, "checks": checks}


def format_report(report: dict) -> str:
    mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    lines = [f"QC {Path(report['video']).name}: "
             f"{'PASS' if report['ok'] else 'FAIL'}"]
    lines += [f"  [{mark[c['status']]}] {c['name']}: {c['detail']}"
              for c in report["checks"]]
    return "\n".join(lines)
