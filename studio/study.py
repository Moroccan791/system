"""Read a reference edit and report its INVARIANTS, not its description.

The difference matters and it cost us a build:

  * a DESCRIPTION says "the type stacks four lines and accumulates". Copying that
    produces a screen full of paragraphs the moment the footage, the song or the
    length changes — which is what happened.
  * an INVARIANT says "type occupies 55% of the runtime, never more than one
    register at a time, and clears for the last 2 s". That survives a change of
    material, so it can become a rule in the engine.

`study.py` reads a file once and prints whichever of the two it can actually
prove: every number below is measured from pixels and samples, at frame
precision, and each one is written to JSON so two files can be compared instead
of eyeballed.

    python -m studio.study ref.mp4 --json work/study/ref.json --sheet work/study/ref.jpg

    python -m studio.study --compare a.json b.json

What it measures, in order:

    STRUCTURE  hard cuts at frame accuracy, cut / dissolve / blur-whip classified,
               shot lengths, longest hold, motion profile inside each shot
    TYPE       white and coloured type masked per frame, merged into runs, with
               on-screen percentage, how many lines at once, and when it clears
    SOUND      level map, true-silence runs, kick-band events, and how many cuts
               land on a kick (split before/after the drop)
    GRADE      median luma, saturation, shadow tint, blown-highlight share

Nothing here guesses. If a measurement cannot be made on a file — a silent
source, a file with no type — the section says so rather than printing a zero
that reads like a finding.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

# --- what counts as a measurement -------------------------------------------
# TOLERANCE. On a 2.4:1 film letterboxed into a 16:9 file, motion is measured
# across a small picture, and the detector lands within about +/-20% of a hand
# count (33 vs 24 on the reference, with every one of the 24 found). That is good
# enough for the job it exists to do — comparing files with ONE instrument, where
# a consistent bias cancels — and it is not good enough to quote as a cut count.
# Absolute numbers from this module carry that caveat; comparisons do not.
CUT_FRAME_DIFF = 3.2      # a cut is this many times the local motion
CUT_HIST = 0.09           # and this much colour-histogram change
BLUR_RUN = 12             # sustained motion this many frames = a blur, not a cut
FREEZE_DIFF = 0.30
SILENCE_DB = -95.0
KICK = (35, 130)          # Hz
TYPE_MIN_PX = 0.0004      # share of frame a type mask needs to count


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(path: str | Path) -> dict:
    out = subprocess.run([ffmpeg(), "-nostdin", "-i", str(path)],
                         capture_output=True, text=True).stderr
    info = {"w": 0, "h": 0, "fps": 0.0, "dur": 0.0, "audio": False}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            info["dur"] = int(h) * 3600 + int(m) * 60 + float(s)
        elif "Video:" in line:
            import re

            hit = re.search(r"(?<![\d.])(\d{2,5})x(\d{2,5})(?![\d.])", line)
            if hit:
                info["w"], info["h"] = int(hit.group(1)), int(hit.group(2))
            f = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
            if f:
                info["fps"] = float(f.group(1))
        elif "Audio:" in line:
            info["audio"] = True
    if not info["fps"]:
        info["fps"] = 30.0
    return info


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
def _frames(path: str, info: dict, w: int = 240) -> tuple[np.ndarray, np.ndarray]:
    """Every frame: small RGB for colour work, grey for motion."""
    h = max(2, int(round(w * info["h"] / max(1, info["w"]))))
    raw = subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-i", path,
         "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    rgb = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    grey = (rgb.astype(np.float32) * [0.2126, 0.7152, 0.0722]).sum(axis=3)
    return rgb, grey


def _histocolour(rgb: np.ndarray) -> np.ndarray:
    """Per-frame 3x16 colour histogram — a cut changes the palette, motion does not."""
    n = len(rgb)
    out = np.zeros((n, 48), np.float32)
    for i in range(n):
        for c in range(3):
            hh, _ = np.histogram(rgb[i, ..., c], bins=16, range=(0, 256))
            out[i, c * 16: (c + 1) * 16] = hh / max(1, hh.sum())
    return out


def structure(path: str, info: dict) -> dict:
    rgb, grey = _frames(path, info)
    fps = info["fps"]
    n = len(grey)
    if n < 4:
        return {"error": "no frames decoded"}
    diff = np.abs(np.diff(grey, axis=0)).mean(axis=(1, 2))
    hist = _histocolour(rgb)
    hd = np.zeros(n, np.float32)
    for i in range(1, n):
        p, q = hist[i - 1], hist[i]
        hd[i] = 0.5 * float(np.sum((p - q) ** 2 / (p + q + 1e-9)))

    # A cut is a spike against the LOCAL motion, not an absolute number — a
    # whip-pan and a hard cut both move a lot of pixels. What separates them is
    # that a cut is one frame wide and the motion either side of it is
    # unrelated to it.
    #
    # The colour histogram is a BOOSTER, never a gate: measured on the reference,
    # three of its six opening cuts change the palette by under 1% (same room,
    # new angle) and a histogram test alone silently dropped them.
    cuts: list[int] = []
    for i in range(3, n - 3):
        win = np.concatenate([diff[max(0, i - 9):i - 1], diff[i + 2:i + 10]])
        local = float(np.median(win)) if len(win) else 1.0
        spike = diff[i] / max(local, 0.5)
        strong = spike > 3.2 and diff[i] > 9.0
        if hd[i] > CUT_HIST:
            strong = strong or (spike > 1.8 and diff[i] > 12.0)
        if strong and (not cuts or i - cuts[-1] > 2):
            cuts.append(i)

    bounds = [0] + cuts + [n]
    shots = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 2:
            continue
        seg = diff[a + 1:b - 1] if b - a > 4 else np.array([], dtype=diff.dtype)
        if len(seg) < 2:
            seg = np.array([0.0, 0.0], dtype=diff.dtype)
        half = max(1, len(seg) // 2)
        m0, m1 = float(seg[:half].mean()), float(seg[half:].mean())
        if seg.mean() < FREEZE_DIFF:
            motion = "frozen"
        elif m1 > 1.6 * max(m0, 1e-6):
            motion = "accelerating"
        elif m1 < 0.62 * max(m0, 1e-6):
            motion = "decelerating"
        elif seg.mean() < 1.2:
            motion = "near-still"
        else:
            motion = "steady"
        shots.append({"in": round(a / fps, 3), "out": round(b / fps, 3),
                      "len": round((b - a) / fps, 3), "motion": motion,
                      "motion_ratio": round(m1 / max(m0, 1e-6), 2)})

    # blur-whips: long stretches of heavy continuous motion with no still frame
    blur = []
    i = 0
    while i < n - BLUR_RUN:
        if float(np.median(diff[i:i + BLUR_RUN])) > 8.0 and diff[i:i + BLUR_RUN].min() > 3.0:
            j = i
            while j < n - 1 and diff[j] > 3.0:
                j += 1
            if j - i >= BLUR_RUN:
                blur.append((round(i / fps, 2), round(j / fps, 2)))
            i = j
        else:
            i += 1

    lens = np.array([s["len"] for s in shots]) if shots else np.array([0.0])
    holds = [s for s in shots if s["len"] >= 4.0]
    return {
        "fps": fps, "frames": n, "duration": round(n / fps, 2),
        "cuts": len(cuts),
        "cut_times": [round(c / fps, 3) for c in cuts],
        "shots": shots,
        "shot_len": {"min": round(float(lens.min()), 2),
                     "median": round(float(np.median(lens)), 2),
                     "mean": round(float(lens.mean()), 2),
                     "max": round(float(lens.max()), 2)},
        "holds_4s": [{"in": h["in"], "len": h["len"], "motion": h["motion"]}
                     for h in holds],
        "share_in_holds": round(sum(h["len"] for h in holds) / max(1e-6, n / fps), 3),
        "blur_whips": blur,
    }


# ---------------------------------------------------------------------------
# type
# ---------------------------------------------------------------------------
def _mask_white(rgb: np.ndarray) -> np.ndarray:
    """One frame, (h, w, 3): near-white and near-neutral."""
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    return (mn > 205) & ((mx - mn) < 30)


def _mask_red(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 95) & (r < 220) & (g < 60) & (b < 70)


def typography(path: str, info: dict, fps_sample: float = 10.0) -> dict:
    """Type inventory: when it is on, how big, where, and how long each card lives.

    Deliberately does NOT guess how many lines are on screen. At 320 px a bright
    wall, a window and a white shirt all produce the same mask, and a count built
    on that is a number that reads like a finding and is not one. What is
    reported is what survives: the on/off runs, their length, and the box the
    marks occupy — enough to tell a centred card from a corner block.
    """
    w = 320
    h = max(2, int(round(w * info["h"] / max(1, info["w"]))))
    raw = subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-i", path,
         "-vf", f"fps={fps_sample},scale={w}:{h}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    if n < 2:
        return {"error": "no frames for the type pass"}
    rgb = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)

    rows = []
    for i in range(n):
        f = rgb[i]
        best = None
        for m in (_mask_white(f), _mask_red(f)):
            share = float(m.mean())
            if share < TYPE_MIN_PX or share > 0.14:
                continue
            ys, xs = np.nonzero(m)
            bh = (ys.max() - ys.min()) / h
            bw = (xs.max() - xs.min()) / w
            if bh > 0.55 or bw < 0.05:
                continue        # a lit surface, not a line of type
            if best is None or share > best[4]:
                best = (float(xs.min() / w), float(xs.max() / w),
                        float(ys.min() / h), float(ys.max() / h), share)
        rows.append((i / fps_sample, best))

    runs = []
    cur = None
    for t, box in rows:
        if box and cur is None:
            cur = {"in": t, "out": t + 1 / fps_sample, "box": box}
        elif box and cur is not None:
            cur["out"] = t + 1 / fps_sample
            bx = cur["box"]
            cur["box"] = (min(bx[0], box[0]), max(bx[1], box[1]),
                          min(bx[2], box[2]), max(bx[3], box[3]),
                          max(bx[4], box[4]))
        elif not box and cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)

    runs = [r for r in runs if r["out"] - r["in"] >= 0.15]
    total = n / fps_sample
    covered = sum(min(r["out"], total) - r["in"] for r in runs)
    lengths = [r["out"] - r["in"] for r in runs]
    centres = [((r["box"][0] + r["box"][1]) / 2, (r["box"][2] + r["box"][3]) / 2)
               for r in runs]
    return {
        "sample_fps": fps_sample,
        "on_screen_share": round(covered / max(1e-6, total), 3),
        "runs": len(runs),
        "run_len": {"median": round(float(np.median(lengths)), 2) if lengths else 0,
                    "min": round(min(lengths), 2) if lengths else 0,
                    "max": round(max(lengths), 2) if lengths else 0},
        "centre": [round(float(np.median([c[0] for c in centres])), 2) if centres else None,
                   round(float(np.median([c[1] for c in centres])), 2) if centres else None],
        "width": round(float(np.median([(r["box"][1] - r["box"][0])
                                        for r in runs])), 2) if runs else None,
        "height": round(float(np.median([(r["box"][3] - r["box"][2])
                                         for r in runs])), 2) if runs else None,
        "first_at": round(runs[0]["in"], 2) if runs else None,
        "clears_before_end": round(total - runs[-1]["out"], 2) if runs else None,
        "windows": [{"in": round(r["in"], 2), "out": round(r["out"], 2),
                     "w": round(r["box"][1] - r["box"][0], 2),
                     "y": round((r["box"][2] + r["box"][3]) / 2, 2)}
                    for r in runs],
    }


# ---------------------------------------------------------------------------
# sound
# ---------------------------------------------------------------------------
def sound(path: str, info: dict) -> dict:
    if not info["audio"]:
        return {"error": "no audio stream"}
    sr = 22050
    raw = subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-i", path, "-ac", "1",
         "-ar", str(sr), "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    if len(a) < sr:
        return {"error": "audio too short"}
    w = int(sr * 0.25)
    n = len(a) // w
    rms = np.sqrt((a[: n * w].reshape(n, w) ** 2).mean(1))
    db = 20 * np.log10(np.maximum(rms, 1e-6))

    sil = db < SILENCE_DB
    runs = []
    st = None
    for i, v in enumerate(sil):
        if v and st is None:
            st = i
        if not v and st is not None:
            if (i - st) * 0.25 >= 0.15:
                runs.append((round(st * 0.25, 2), round(i * 0.25, 2)))
            st = None
    if st is not None and (n - st) * 0.25 >= 0.15:
        runs.append((round(st * 0.25, 2), round(n * 0.25, 2)))

    from numpy.fft import irfft, rfft, rfftfreq

    A = rfft(a)
    f = rfftfreq(len(a), 1 / sr)
    A[(f < KICK[0]) | (f > KICK[1])] = 0
    low = irfft(A)
    kw = int(sr * 0.02)
    kn = len(low) // kw
    env = np.sqrt((low[: kn * kw].reshape(kn, kw) ** 2).mean(1))
    thr = np.percentile(env, 92)
    pk = [i for i in range(1, kn - 1)
          if env[i] > thr and env[i] >= env[i - 1] and env[i] >= env[i + 1]]
    kicks: list[float] = []
    for p in pk:
        x = p * 0.02
        if not kicks or x - kicks[-1] > 0.12:
            kicks.append(round(x, 3))

    return {
        "level_db": {"mean": round(float(db[~sil].mean()), 1) if (~sil).any() else None,
                     "min": round(float(db[~sil].min()), 1) if (~sil).any() else None,
                     "max": round(float(db[~sil].max()), 1) if (~sil).any() else None},
        "silences": runs,
        "silence_share": round(sum(b - a_ for a_, b in runs) / max(1e-6, n * 0.25), 3),
        "longest_silence": round(max((b - a_ for a_, b in runs), default=0.0), 2),
        "kicks": kicks,
        "first_kick": kicks[0] if kicks else None,
    }


def alignment(struct: dict, snd: dict) -> dict:
    """Do the cuts land on the music? Split at the midpoint, because an edit can
    change its mind halfway through and a single number hides that."""
    cuts = struct.get("cut_times") or []
    kicks = snd.get("kicks") or []
    if not cuts or not kicks:
        return {"error": "needs both cuts and kicks"}
    k = np.array(kicks)
    d = np.array([float(np.abs(k - c).min()) for c in cuts])
    half = len(cuts) // 2
    mid = cuts[half] if cuts else 0
    out = {"median_offset": round(float(np.median(d)), 3),
           "on_kick_80ms": int((d < 0.08).sum()),
           "cuts": len(cuts),
           "split_at": round(mid, 2)}
    for name, sl in (("before", d[:half]), ("after", d[half:])):
        if len(sl):
            out[name] = {"median_offset": round(float(np.median(sl)), 3),
                         "on_kick": int((sl < 0.08).sum()), "n": int(len(sl))}
    return out


# ---------------------------------------------------------------------------
# grade
# ---------------------------------------------------------------------------
def grade_stats(path: str, info: dict) -> dict:
    rgb, grey = _frames(path, info, w=320)
    if len(grey) < 2:
        return {"error": "no frames"}
    f = rgb.astype(np.float32)
    sat = ((f.max(axis=3) - f.min(axis=3)) / (f.max(axis=3) + 1e-6)).mean(axis=(1, 2))
    dark = grey < np.percentile(grey, 50, axis=(1, 2))[:, None, None]
    tint = []
    for i in range(len(grey)):
        m = dark[i]
        if m.sum():
            tint.append([f[i, ..., c][m].mean() for c in range(3)])
    tint = np.array(tint).mean(0)
    return {
        "luma_mean": round(float(grey.mean()), 1),
        "luma_median": round(float(np.median(grey)), 1),
        "luma_p10": round(float(np.percentile(grey, 10)), 1),
        "luma_p90": round(float(np.percentile(grey, 90)), 1),
        "saturation": round(float(sat.mean()), 3),
        "shadow_rgb": [round(float(v), 1) for v in tint],
        "shadow_ratio": [round(float(v / max(1e-6, tint.max())), 3) for v in tint],
        "blown_share": round(float((grey > 235).mean()), 4),
    }


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def study(path: str | Path, sheet: str | None = None) -> dict:
    info = probe(path)
    out = {"file": str(path), "probe": info}
    out["structure"] = structure(str(path), info)
    out["type"] = typography(str(path), info)
    out["sound"] = sound(str(path), info)
    out["alignment"] = alignment(out["structure"], out["sound"])
    out["grade"] = grade_stats(str(path), info)
    if sheet:
        _sheet(str(path), info, sheet)
        out["sheet"] = sheet
    return out


def _sheet(path: str, info: dict, out: str, cols: int = 8, every: float = 1.5) -> None:
    from PIL import Image, ImageDraw

    w = 200
    h = max(2, int(round(w * info["h"] / max(1, info["w"]))))
    raw = subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-i", path,
         "-vf", f"fps=1/{every},scale={w}:{h}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    if not n:
        return
    frames = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    rows = (n + cols - 1) // cols
    canvas = Image.new("RGB", (cols * w, rows * (h + 12)), "black")
    d = ImageDraw.Draw(canvas)
    for i in range(n):
        x, y = (i % cols) * w, (i // cols) * (h + 12)
        canvas.paste(Image.fromarray(frames[i]), (x, y + 12))
        d.text((x + 3, y), f"{i * every:.1f}s", fill=(255, 255, 0))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=86)


def compare(a: dict, b: dict) -> str:
    """Two studies side by side. What is the SAME across files is a rule; what
    differs is a style choice — and only the rules are worth building."""
    def g(d, *keys, default=None):
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    rows = [
        ("duration", g(a, "structure", "duration"), g(b, "structure", "duration")),
        ("cuts", g(a, "structure", "cuts"), g(b, "structure", "cuts")),
        ("median shot", g(a, "structure", "shot_len", "median"),
         g(b, "structure", "shot_len", "median")),
        ("longest shot", g(a, "structure", "shot_len", "max"),
         g(b, "structure", "shot_len", "max")),
        ("share in 4s+ holds", g(a, "structure", "share_in_holds"),
         g(b, "structure", "share_in_holds")),
        ("type on screen", g(a, "type", "on_screen_share"),
         g(b, "type", "on_screen_share")),
        ("max lines at once", g(a, "type", "max_lines_at_once"),
         g(b, "type", "max_lines_at_once")),
        ("type clears before end", g(a, "type", "clears_before_end"),
         g(b, "type", "clears_before_end")),
        ("cuts on kick", g(a, "alignment", "on_kick_80ms"),
         g(b, "alignment", "on_kick_80ms")),
        ("median cut/kick offset", g(a, "alignment", "median_offset"),
         g(b, "alignment", "median_offset")),
        ("silence share", g(a, "sound", "silence_share"),
         g(b, "sound", "silence_share")),
        ("longest silence", g(a, "sound", "longest_silence"),
         g(b, "sound", "longest_silence")),
        ("median luma", g(a, "grade", "luma_median"), g(b, "grade", "luma_median")),
        ("saturation", g(a, "grade", "saturation"), g(b, "grade", "saturation")),
        ("blown highlights", g(a, "grade", "blown_share"),
         g(b, "grade", "blown_share")),
    ]
    wa = max(len(str(r[0])) for r in rows)
    out = [f"{'':<{wa}}  {'A':>12}  {'B':>12}"]
    for name, va, vb in rows:
        out.append(f"{name:<{wa}}  {str(va):>12}  {str(vb):>12}")
    return "\n".join(out)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="read a reference edit for its invariants")
    ap.add_argument("video", nargs="?", default=None)
    ap.add_argument("--json", default=None, help="write the full study here")
    ap.add_argument("--sheet", default=None, help="write a contact sheet here")
    ap.add_argument("--compare", nargs=2, default=None, metavar=("A", "B"),
                    help="compare two study json files")
    a = ap.parse_args(argv)
    if a.compare:
        print(compare(json.loads(Path(a.compare[0]).read_text()),
                      json.loads(Path(a.compare[1]).read_text())))
        return 0
    if not a.video:
        raise SystemExit("give a video, or --compare A.json B.json")
    s = study(a.video, a.sheet)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(s, indent=1) + "\n")
    st, ty, so, al, gr = (s["structure"], s["type"], s["sound"],
                          s["alignment"], s["grade"])
    print(f"{Path(a.video).name}  {s['probe']['w']}x{s['probe']['h']}  "
          f"{st.get('duration')}s  {st.get('cuts')} cuts")
    print(f"  shot len   min {st['shot_len']['min']}  median "
          f"{st['shot_len']['median']}  max {st['shot_len']['max']}")
    print(f"  holds 4s+  {len(st['holds_4s'])} ({st['share_in_holds']:.0%} of runtime)")
    print(f"  blur-whips {len(st['blur_whips'])}")
    print(f"  type       on screen {ty.get('on_screen_share', 0):.0%}, "
          f"max {ty.get('max_lines_at_once')} line(s) at once, "
          f"clears {ty.get('clears_before_end')}s before end")
    print(f"  cuts/kick  {al.get('on_kick_80ms')}/{al.get('cuts')} within 80ms "
          f"(median offset {al.get('median_offset')}s)")
    print(f"  silence    {so.get('silence_share', 0):.0%} of runtime, "
          f"longest {so.get('longest_silence')}s")
    print(f"  grade      luma median {gr.get('luma_median')}, sat "
          f"{gr.get('saturation')}, blown {gr.get('blown_share'):.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
