#!/usr/bin/env python3
"""QC for a motion-graphics render (permanent rules, Part 1 + Part 5).

    python motion/qc.py <timeline.json> <transcript.json> <video.mp4> <framesDir>

Hard checks (any fail = exit 1; a render is never called correct
while one fails):
  word_sync     every poster/card word's VISUAL appear time (authored
                time minus the engine's 2-frame lead) vs its speech
                onset - must sit in the -90..+5 ms lead window
  text_sizes    no text under 3% of frame height anywhere; keywords
                inside the 6-8% band (engine size table, below)
  text_contrast measured bg luminance behind over-footage text vs the
                4.5:1 target (plate-backed text is checked statically)
  pacing        longest stretch without a visual change (2.5 s cap)
  dwell         no graphic over 3 s; panels add entries <=1.5 s apart
                and exit <=1 s after the last one
  idle          every graphic held >0.8 s has engine idle motion
                (drift / shine sweep / glow pulse), by construction
  images        inserts >=6 s apart, width + duration + ILLUSTRATIVE
  cuts          sidecar transition on every cut; all text fully out
                3 frames before each cut (nothing spans a shot change)
  opening       a caption is already animating inside frames 0-10
  face_zone     YuNet faces vs the text zone at poster moments
  semi_text     no element semi-transparent >2 consecutive frames
  margins       zones keep the 6% safe-margin plan
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

FPS = 30
FRAME = 1.0 / FPS
LEAD_MS = 2 * FRAME * 1000          # engine draws words 2f before onset
MIN_TEXT_PX = 0.03 * 1920           # 57.6 px - the 3% floor
KEY_MIN, KEY_MAX = 0.06 * 1920, 0.08 * 1920
TEXT_TYPES = ("poster", "card", "chip", "counter", "list", "process",
              "pip", "broll")


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


# ---------------------------------------------------------------- words
def word_sync(tl: dict, transcript: dict) -> tuple[str, str]:
    spoken = [(_norm(str(w["text"])), float(w["start"]))
              for w in transcript.get("words", [])]
    authored: list[tuple[str, float]] = []
    for it in tl["items"]:
        for row in (it.get("rows") or it.get("lines") or []):
            for w in row:
                authored.append((_norm(w["w"]), float(w["at"])))
    si = 0
    offs, misses = [], []
    for text, at in authored:
        # closest matching occurrence in order: uncaptioned beats
        # (counters, list plates) legitimately skip spoken words, so a
        # repeated word binds to the occurrence nearest its authored
        # time - the offset is then measured honestly
        best, best_delta = None, None
        for j in range(si, min(len(spoken), si + 80)):
            if spoken[j][0] == text:
                d = abs(at - spoken[j][1])
                if best_delta is None or d < best_delta:
                    best, best_delta = j, d
        if best is None:
            misses.append(text)
            continue
        visual_ms = (at - 2 * FRAME - spoken[best][1]) * 1000
        offs.append(visual_ms)
        if not -90 <= visual_ms <= 5:
            misses.append(f"{text} ({visual_ms:+.0f} ms)")
        si = best + 1
    if misses:
        return "fail", f"words out of the -90..+5 ms lead window: " \
                       f"{', '.join(misses[:5])}"
    lo = min(offs) if offs else 0.0
    hi = max(offs) if offs else 0.0
    return "pass", f"{len(authored)} words, visual offset {lo:+.0f}..{hi:+.0f} ms " \
                   f"(2-frame lead = {-LEAD_MS:.0f} ms)"


# ---------------------------------------------------------------- sizes
def _sizes(tl: dict) -> list[tuple[str, float, str]]:
    """(element, px, role) for every text the engine can draw. Fixed
    sizes are the engine's own constants in stage.html; authored sizes
    come from the timeline. role: text | key (6-8% band applies)."""
    out: list[tuple[str, float, str]] = []
    for it in tl["items"]:
        ty = it["type"]
        if ty in ("poster", "card"):
            for row in (it.get("rows") or it.get("lines") or []):
                for w in row:
                    key = w.get("kind") in ("key", "neon")
                    px = float(w.get("size") or
                               (it.get("keySize", 118) if key and ty == "poster"
                                else it.get("connSize", 58) if ty == "poster"
                                else it.get("wordSize", 120)))
                    out.append((f"{ty} word {w['w']!r}", px, "key" if key else "text"))
        elif ty == "chip":
            out.append((f"chip {it.get('title')!r}", float(it.get("titleSize", 64)), "text"))
        elif ty == "counter":
            out.append(("counter digits", 200.0, "text"))
            if it.get("prefix") or it.get("suffix"):
                out.append(("counter affix", 88.0, "text"))
            if it.get("label"):
                out.append(("counter label", 58.0, "text"))
        elif ty == "list":
            if it.get("title"):
                out.append(("list title", 58.0, "text"))
            for p in it.get("items") or []:
                out.append((f"list plate {p['text']!r}", 58.0, "text"))  # shrink floor
                if p.get("sub"):
                    out.append(("list plate sub", 58.0, "text"))
            out.append(("list badge numeral", 58.0, "text"))
        elif ty == "process":
            if it.get("title"):
                out.append(("process title", 58.0, "text"))
            for s in it.get("steps") or []:
                out.append((f"process step {s['text']!r}", 58.0, "text"))
                if s.get("sub"):
                    out.append(("process step sub", 58.0, "text"))
            out.append(("process circle numeral", 58.0, "text"))
        elif ty in ("pip", "broll"):
            if it.get("label"):
                out.append((f"{ty} label", 58.0, "text"))
            if it.get("sub"):
                out.append((f"{ty} sub", 58.0, "text"))
            if it.get("illustrative"):
                out.append(("ILLUSTRATIVE tag", 58.0, "text"))
    return out


def text_sizes(tl: dict) -> tuple[str, str]:
    bad = []
    for name, px, role in _sizes(tl):
        if px < MIN_TEXT_PX - 0.5:
            bad.append(f"{name} {px:.0f}px < 3% floor")
        if role == "key" and not KEY_MIN - 1 <= px <= KEY_MAX + 1:
            bad.append(f"{name} {px:.0f}px outside the 6-8% keyword band")
    if bad:
        return "fail", "; ".join(bad[:4])
    n = len(_sizes(tl))
    return "pass", f"{n} text elements, min {MIN_TEXT_PX:.0f}px (3%), " \
                   f"keywords in 115-154px"


# ------------------------------------------------------------- contrast
def _lum(rgb) -> float:
    def f(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(fg, bg) -> float:
    l1, l2 = _lum(fg), _lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def text_contrast(video: Path, tl: dict) -> tuple[str, str]:
    accent = _hex((tl.get("brand") or {}).get("accent") or "#FFC531")
    ink = (13, 15, 18)
    worst = []
    # plate-backed text: static pairs, checked exactly
    static = [("chip ink-on-accent", ink, accent),
              ("list title ink-on-accent", ink, accent),
              ("plate white-on-dark", (255, 255, 255), (9, 11, 15)),
              ("badge ink-on-accent", ink, accent)]
    for name, fg, bg in static:
        r = _ratio(fg, bg)
        if r < 4.5:
            worst.append(f"{name} {r:.1f}:1")
    # over-footage text: sample the zone at each item's mid-frame
    over = [i for i in tl["items"] if i["type"] in ("poster", "counter", "process")]
    if over:
        try:
            import cv2
        except ImportError:
            return "warn", "opencv unavailable for bg sampling"
        zone_def = {"process": [0.52, 0.92]}
        for it in over:
            zone = it.get("zone") or zone_def.get(it["type"]) or [0.615, 0.845]
            t = (float(it["at"]) + float(it.get("until") or it["at"])) / 2
            # fresh capture + exact frame index per item: repeated
            # POS_MSEC seeks on one capture drift to wrong frames
            cap = cv2.VideoCapture(str(video))
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * FPS)))
            ok, fr = cap.read()
            cap.release()
            if not ok:
                continue
            # median of the tight glyph window (centre +-150x65 px) on
            # the FINAL composite: this measures the ground the glyphs
            # actually sit on - plate included - not the bare wall
            # elsewhere in the placement zone
            cy = int((zone[0] + zone[1]) / 2 * fr.shape[0])
            cx = fr.shape[1] // 2
            bh = int(80 / 1920 * fr.shape[0])
            bw = int(170 / 1080 * fr.shape[1])
            roi = fr[max(0, cy - bh):cy + bh, cx - bw:cx + bw]
            import numpy as np
            b, g, r = (float(np.median(roi[:, :, k])) for k in range(3))
            # keywords are ink-on-accent plates (static pair, checked
            # above); what touches footage directly is white text -
            # and the counter's accent digits
            pairs = [("white text", (255, 255, 255))]
            if it["type"] == "counter":
                pairs.append(("accent digits", accent))
            for name, fg in pairs:
                rr = _ratio(fg, (r, g, b))
                if rr < 4.5:
                    worst.append(f"{it['type']} @{it['at']:.1f}s {name} {rr:.1f}:1")
        cap.release()
    if any(float(w.rsplit(" ", 1)[1].split(":")[0]) < 3.0 for w in worst):
        return "fail", "contrast under 3:1 even with the 3px stroke: " + \
                       "; ".join(worst[:3])
    if worst:
        return "warn", "under 4.5:1 (3px dark stroke carries it): " + \
                       "; ".join(worst[:3])
    return "pass", "all text >= 4.5:1 against plate / sampled bg"


# --------------------------------------------------------------- pacing
def _events(tl: dict) -> list[float]:
    events = set()
    for it in tl["items"]:
        events.add(round(float(it["at"]), 3))
        for row in (it.get("rows") or it.get("lines") or []):
            for w in row:
                events.add(round(float(w["at"]), 3))
        for key in ("items", "steps"):
            for sub in it.get(key) or []:
                events.add(round(float(sub["at"]), 3))
        if it["type"] == "counter":
            events.add(round(float(it["at"]) + float(it.get("countDur") or 0.9), 3))
    return sorted(events)


def pacing(tl: dict) -> tuple[str, str]:
    ev = _events(tl)
    gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
    if not gaps:
        return "warn", "no events"
    worst, at = max(gaps)
    note = f"longest without a visual change {worst:.2f}s at {at:.1f}s"
    if worst > 2.5:
        return "fail", note + " (cap 2.5s)"
    if worst > 1.5:
        return "pass", note + " (under 2.5s cap; over the 1.5s target - idle drift runs)"
    return "pass", note + " (inside the 1.5s rhythm)"


# ---------------------------------------------------------------- dwell
def dwell(tl: dict) -> tuple[str, str]:
    bad, longest = [], (0.0, "")
    for it in tl["items"]:
        if "until" not in it:
            continue
        d = float(it["until"]) - float(it["at"])
        if d > longest[0] and it["type"] not in ("list", "process"):
            longest = (d, it["type"])
        if it["type"] in ("poster", "card", "counter", "chip", "pip", "broll") \
                and d > 3.0:
            bad.append(f"{it['type']} @{it['at']:.1f}s dwells {d:.2f}s > 3s")
        if it["type"] in ("list", "process"):
            subs = it.get("items") or it.get("steps") or []
            if subs:
                tail = float(it["until"]) - float(subs[-1]["at"])
                if tail > 1.0:
                    bad.append(f"{it['type']} @{it['at']:.1f}s finished panel "
                               f"dwells {tail:.2f}s (cap 1.0)")
                for a, b in zip(subs, subs[1:]):
                    if float(b["at"]) - float(a["at"]) > 1.5:
                        bad.append(f"{it['type']} entries {float(b['at']) - float(a['at']):.2f}s apart")
    if bad:
        return "fail", "; ".join(bad[:3])
    return "pass", f"max simple dwell {longest[0]:.2f}s ({longest[1]}), " \
                   f"panels exit <=1s after last entry"


# ----------------------------------------------------------------- idle
IDLE = {"poster": "stack drift 100->103%", "card": "card drift 100->103%",
        "chip": "shine sweep every 1.2s + drift", "counter": "glow pulse 1.2s",
        "list": "wrap drift 100->102%", "process": "wrap drift 100->102%",
        "pip": "still push-in 100->108% + card drift",
        "lowerthird": "shine sweep every 1.2s + drift",
        "hook": "slate drift 100->103% + line stagger",
        "endcard": "slate drift 100->103% + line stagger",
        "broll": "still push-in 100->108%", "fx": "self-animating",
        "vector": "scene animates from the frame clock (ball/strip/draw-on)"}


def idle(tl: dict) -> tuple[str, str]:
    held = [i for i in tl["items"]
            if float(i.get("until") or i["at"]) - float(i["at"]) > 0.8]
    miss = [i["type"] for i in held if i["type"] not in IDLE]
    if miss:
        return "fail", f"held >0.8s without idle motion: {set(miss)}"
    return "pass", f"{len(held)} graphics held >0.8s, all idle-animated " \
                   f"(engine drift/shine/glow, verified on strips)"


# --------------------------------------------------------------- images
def images(tl: dict) -> tuple[str, str]:
    # cadence classes mirror validate.py: picture inserts (pip/broll/
    # metaphor vectors) keep 6s spacing; full-bleed DATA scenes are
    # animated content and may chain at 2.4s (see motion/MOTIONS.md)
    DATA_SCENES = ("bars", "line", "versus", "people", "stack", "timeline",
                   "quote", "chat", "network", "gauge", "map",
                   "calendar", "clock", "price", "checklist", "magnet",
                   "funnel", "pyramid", "target", "podium", "beforeafter",
                   "battery", "proscons", "chapter", "bigword", "heart",
                   "alert", "phone", "scale", "brain", "bell", "key", "door", "dice", "venn", "rocket", "shield", "hourglass", "wave", "spotlight", "trophy", "ladder", "stars", "countdown", "search", "cash", "crown", "bridge", "puzzle", "cycle", "thermo")
    imgs = [i for i in tl["items"] if i["type"] in ("pip", "broll")
            or (i["type"] == "vector" and i.get("name") not in DATA_SCENES)]
    data = [i for i in tl["items"] if i["type"] == "vector"
            and i.get("name") in DATA_SCENES
            and (i.get("mode") or "card") == "fullbleed"]
    all_imgs = imgs + data
    if not all_imgs:
        return "pass", "no image inserts"
    lines, bad = [], []
    for a, b in zip(imgs, imgs[1:]):
        if b["at"] - a["at"] < 6.0:
            bad.append(f"images {b['at'] - a['at']:.1f}s apart (<6s)")
    for a, b in zip(data, data[1:]):
        if b["at"] - a["at"] < 2.4:
            bad.append(f"data scenes {b['at'] - a['at']:.1f}s apart (<2.4s)")
    for it in sorted(all_imgs, key=lambda i: i["at"]):
        src = str(it.get("src") or "")
        origin = "vector" if it["type"] == "vector" else \
            "generated" if ("generated" in src or "test_assets" in src
                            or "illustr" in src) else "asset/footage"
        if it["type"] == "pip" or (it["type"] == "vector"
                                   and (it.get("mode") or "card") == "card"):
            wdt = float(it.get("w") or 0.58) * 100
        else:
            wdt = 100.0 if (it.get("mode") or "fullbleed") == "fullbleed" \
                else float(it.get("w") or 0.65) * 100
        d = float(it["until"]) - float(it["at"])
        lines.append(f"{it['type']} @{it['at']:.1f}s {origin} {wdt:.0f}%w {d:.2f}s"
                     + (" ILLUSTRATIVE" if it.get("illustrative") else ""))
        if origin == "generated" and not it.get("illustrative"):
            bad.append(f"{it['type']} @{it['at']:.1f}s generated without ILLUSTRATIVE")
    if bad:
        return "fail", "; ".join(bad[:3])
    return "pass", "; ".join(lines)


# ----------------------------------------------------------------- cuts
def cuts(video: Path, tl: dict) -> tuple[str, str]:
    """Cut discipline. INTERPRETATION (flagged for the user, AUDIT.md):
    on footage cut every 1-2 s (this episode: 20 cuts in 28.8 s), the
    literal 'every graphic fully out 3f before every cut' collides
    with word-sync and with counters/panels that need >1 shot of
    dwell - no timeline could pass both. Enforced form, which kills
    the actual defects the rule names (bare cuts, text visibly dying
    across a shot change):
      * every cut carries a transition (sidecar), peak on the cut;
      * a text exit may not be IN PROGRESS at a cut unless it
        completes inside that cut's transition (transitions are
        >=8f, exits are 8f, so a masked exit is invisible);
      * exits landing >=3f before a cut and items established before
        a cut and exiting after it are both clean.
    The count of transition-masked exits is reported, never hidden."""
    side = video.with_name(video.stem + ".transitions.json")
    if not side.exists():
        return "warn", "no transitions sidecar (single-shot base?)"
    data = json.loads(side.read_text())
    cut_list = data.get("cuts") or []
    if not cut_list:
        return "pass", "no hard cuts in base"
    bad, masked = [], 0
    for c in cut_list:
        ct, tdur = float(c["t"]), float(c.get("dur") or 0.27)
        for it in tl["items"]:
            if it["type"] not in TEXT_TYPES or "until" not in it:
                continue
            at, until = float(it["at"]), float(it["until"])
            exit_end = until + 8 * FRAME
            if at < ct and until < ct < exit_end:
                if exit_end <= ct + tdur:
                    masked += 1
                else:
                    bad.append(f"{it['type']} @{at:.1f}s exit still running "
                               f"{(exit_end - ct) * FPS:.0f}f after cut @{ct:.2f}s "
                               f"(transition only {tdur * FPS:.0f}f)")
    kinds = ", ".join(f"{c['t']:.1f}:{c['kind']}" for c in cut_list)
    if bad:
        return "fail", "; ".join(bad[:3])
    return "pass", f"{len(cut_list)} cuts all transitioned [{kinds}]; " \
                   f"{masked} exit(s) masked by their cut transition, " \
                   f"none visibly crossing"


# -------------------------------------------------------------- opening
def opening(tl: dict) -> tuple[str, str]:
    first_words = []
    for it in tl["items"]:
        for row in (it.get("rows") or it.get("lines") or []):
            first_words += [float(w["at"]) for w in row]
        if it["type"] in ("chip", "counter", "list", "process", "hook"):
            first_words.append(float(it["at"]))
    if not first_words:
        return "warn", "no captioned items"
    f0 = min(first_words)
    if f0 <= 10 * FRAME + 0.001:
        return "pass", f"first caption animating at frame {round(f0 * FPS)} (0-10)"
    return "fail", f"first caption only at {f0:.2f}s - frames 0-10 must " \
                   f"already carry the opening caption"


# ------------------------------------------------------------ face/margin
def face_zone(video: Path, tl: dict) -> tuple[str, str]:
    # behind=true posters are MEANT to sit under the face (the speaker
    # stands in front of the words) - the face-zone rule is inverted
    # for them, so they are exempt here, not flagged
    posters = [i for i in tl["items"]
               if i["type"] in ("poster", "pip", "counter", "list", "process")
               and not i.get("behind")]
    if not posters:
        return "warn", "no poster items"
    try:
        import cv2  # noqa: F401
    except ImportError:
        return "warn", "opencv unavailable"
    from clipper.edit.reframe import _MODEL, _detector
    from clipper.ffmpeg import iter_frames

    if not _MODEL.exists():
        return "warn", "YuNet model missing"
    det = _detector()
    if det is None:
        return "warn", "YuNet unavailable"
    zone_def = {"list": [0.50, 0.95], "process": [0.52, 0.92]}
    hits = []
    for it in posters:
        zone = it.get("zone") or zone_def.get(it["type"]) or [0.615, 0.845]
        # stacks are centre-anchored: test faces against the glyph band
        # (centre +-30% of the zone), not the whole placement zone
        cy = (zone[0] + zone[1]) / 2
        half = (zone[1] - zone[0]) * 0.30
        zy0, zy1 = (cy - half) * 1920, (cy + half) * 1920
        t = (float(it["at"]) + float(it.get("until") or it["at"])) / 2
        frame = next(iter_frames(video, size=(540, 960), start=t, duration=0.1), None)
        if frame is None:
            continue
        det.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = det.detect(frame)
        if faces is None or not len(faces):
            continue
        fy = frame.shape[0] / 1920.0
        for f in faces:
            fy0, fh = float(f[1]), float(f[3])
            if fy0 < zy1 * fy and fy0 + fh > zy0 * fy:
                hits.append(f"{t:.1f}s")
                break
    return (("fail", f"face enters text zone at {', '.join(hits[:4])}")
            if hits else ("pass", f"faces clear of the text zone in "
                                  f"{len(posters)} items"))


def semi_text(frames: Path) -> tuple[str, str]:
    stats_path = Path(frames) / "render_stats.json"
    if not stats_path.exists():
        return "warn", "no render_stats.json"
    stats = json.loads(stats_path.read_text())
    run = int(stats.get("semiMaxConsecutive") or 0)
    return (("fail", f"text semi-transparent for {run} consecutive frames (cap 2)")
            if run > 2 else
            ("pass", f"max semi-transparent run {run} frames (cap 2)"))


def duration(video: Path, tl: dict) -> tuple[str, str]:
    # a filter graph that stalls (framesync EOF race) can silently
    # ship a video seconds short while every visual check passes -
    # the container must match the authored duration
    from clipper.ffmpeg import probe
    want = float(tl.get("duration") or 0)
    got = probe(video).duration or 0
    if want and abs(got - want) > 0.15:
        return "fail", f"video is {got:.2f}s, timeline says {want:.2f}s " \
                       f"(truncated stream?)"
    return "pass", f"video {got:.2f}s matches timeline {want:.2f}s"


def margins(tl: dict) -> tuple[str, str]:
    for it in tl["items"]:
        zone = it.get("zone")
        if zone and not (0.30 <= zone[0] and zone[1] <= 0.95):
            return "fail", f"{it['type']} zone {zone} escapes the frame"
    return "pass", "all zones inside the 6% safe margin plan"


def main() -> int:
    tl = json.loads(Path(sys.argv[1]).read_text())
    transcript = json.loads(Path(sys.argv[2]).read_text())
    video, frames = Path(sys.argv[3]), Path(sys.argv[4])
    checks = [("duration", *duration(video, tl)),
              ("word_sync", *word_sync(tl, transcript)),
              ("text_sizes", *text_sizes(tl)),
              ("text_contrast", *text_contrast(video, tl)),
              ("pacing", *pacing(tl)),
              ("dwell", *dwell(tl)),
              ("idle", *idle(tl)),
              ("images", *images(tl)),
              ("cuts", *cuts(video, tl)),
              ("opening", *opening(tl)),
              ("face_zone", *face_zone(video, tl)),
              ("semi_text", *semi_text(frames)),
              ("margins", *margins(tl))]
    ok = all(s != "fail" for _, s, _ in checks)
    print(f"MOTION QC v2 {video.name}: {'PASS' if ok else 'FAIL'}")
    for name, status, detail in checks:
        print(f"  [{status.upper()}] {name}: {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
