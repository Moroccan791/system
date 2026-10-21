#!/usr/bin/env python3
"""Cut one moment out of a long episode and finish it for a vertical feed.

This is the generic renderer: `tight_posts.py` is the street campaign's
hand-directed version (one plan file per post, authored zoom keys). Here the
input is a span of a 66-minute episode and the output is a finished short,
using the same pieces:

    layout     16:9 broadcast -> 9:16, nobody cropped
    captions   the spoken words, short lines, key words in the campaign ink
    title      the opening line, top third, for its first beat
    motion     punches on emphasised words
    voice      rumble out, presence in, then loudness to -16 LUFS
    bed        synthesised under the speech, measured against it
    gate       the same manifest + qc_gate, including the DO NOT CLIP check

    render_clip.py --campaign two_bears_ep344 --start 755 --end 795
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR      # noqa: E402
import grade_fast as GR         # noqa: E402
import font_refresh as FR       # noqa: E402
import layout as LY             # noqa: E402
import motion_kit as MK         # noqa: E402
import sound_design as SD       # noqa: E402
import timeline as TL           # noqa: E402
import topic_guard as TG        # noqa: E402
import voice_finish as VF       # noqa: E402

W, H = FR.W, FR.H
KEY_SCALE = 1.16


def ffmpeg() -> str:
    return subprocess.run([sys.executable, "-c",
                           "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                          capture_output=True, text=True).stdout.strip()


#: Words worth setting in the emphasis ink: numbers, absolutes, superlatives.
#: Deliberately small - every extra "key" word makes the emphasis meaningless.
EMPHASIS = re.compile(
    r"^(never|always|nobody|everybody|nothing|everything|best|worst|"
    r"million|billion|thousand|hundred|first|last|only|actually|literally|"
    r"insane|crazy|craziest|funniest|worst|richest|poorest)$", re.I)


def is_key(text: str) -> bool:
    t = str(text).strip().lower().strip(".,!?\"'")
    return bool(EMPHASIS.match(t)) or bool(re.search(r"\d", t))


def build_cards(words: list[dict], *, start: float, end: float) -> list[dict]:
    """Cells -> short-line cards, timed from the words themselves."""
    cells = [{"w": w["text"], "at": float(w["start"]) - start,
              "end": float(w["end"]) - start,
              "kind": "key" if is_key(w["text"]) else "conn"}
             for w in words if start <= float(w["start"]) < end]
    if not cells:
        return []
    cards: list[dict] = []
    for card in CR.wrap_cells(cells):
        line_cells = [c for line in card["lines"] for c in line]
        cards.append({"lines": card["lines"], "zone": "low",
                      "show_from": float(line_cells[0]["at"]),
                      "show_until": float(line_cells[-1]["end"]) + 0.34})
    for a, b in zip(cards, cards[1:]):          # never overlap
        a["show_until"] = min(a["show_until"], b["show_from"] - 0.02)
    return cards


def draw_caption(canvas: np.ndarray, typer: FR.Typesetter, card: dict, t: float,
                 drift: float = 6.0, duration: float = 20.0) -> np.ndarray:
    ov = typer.overlay(card, t)
    shift = int(round(drift * math.sin(2 * math.pi * t / max(duration, 1.0))))
    if shift:
        ov = np.roll(ov, shift, axis=1)
    return blit(canvas, ov)


_BBOX: dict[int, tuple[int, int, int, int]] = {}
_KEEP: dict[int, np.ndarray] = {}        # keep the keyed layer alive: ids are reused


def _first_sentence(words: list[dict], start: float, *, limit: int = 8) -> list[dict]:
    """The opening words, up to the first full stop and at most `limit` long."""
    out: list[dict] = []
    for w in words:
        if float(w["start"]) < start - 0.01:
            continue
        out.append({"w": w["text"], "at": float(w["start"]) - start,
                    "end": float(w["end"]) - start,
                    "kind": "key" if is_key(w["text"]) else "conn"})
        if len(out) >= limit or str(w["text"]).rstrip('"\')').endswith((".", "?", "!")):
            break
    return out


def brand_layer(style: dict, *, line1: str, line2: str, y: int = 1170) -> np.ndarray:
    """An on-screen credit for the show and episode, in the campaign's inks.

    Two jobs at once. The brief's payout condition is that every post carries
    the episode name, and a viewer who screenshots a clip should still be able
    to find the show from the picture alone. It also fills the band between the
    panel and the captions, which is otherwise three hundred pixels of blurred
    backdrop - space that reads as a mistake rather than as air.
    """
    from PIL import Image, ImageDraw, ImageFont
    ink = FR.hex_rgb(style["colors"]["accent"])
    white = FR.hex_rgb(style["colors"]["caption"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FR.font_path(style.get("caption") or style.get("font")), 86)
    f2 = ImageFont.truetype(FR.font_path(style.get("caption") or style.get("font")), 52)
    w1 = d.textlength(line1, font=f1)
    w2 = d.textlength(line2, font=f2)
    d.text(((W - w1) / 2, y), line1, font=f1, fill=ink + (255,),
           stroke_width=3, stroke_fill=(0, 0, 0, 130))
    d.text(((W - w2) / 2, y + 96), line2, font=f2, fill=white + (235,),
           stroke_width=2, stroke_fill=(0, 0, 0, 110))
    return np.asarray(img)


def blit(canvas: np.ndarray, ov: np.ndarray, opacity: float = 1.0) -> np.ndarray:
    """Composite an RGBA layer onto the canvas, inside the layer's own box only.

    Blending a full 1080x1920 frame of float32 for a caption that occupies a
    1080x180 strip is 90% waste, and on this campaign it was most of the
    per-frame budget. The box is cached per layer object, because the
    typesetter caches its layers too.
    """
    box = _BBOX.get(id(ov))
    if box is None:
        alpha = ov[:, :, 3]
        ys = np.flatnonzero(alpha.max(axis=1))
        xs = np.flatnonzero(alpha.max(axis=0))
        if not len(ys) or not len(xs):
            return canvas
        box = (int(ys[0]), int(ys[-1]) + 1, int(xs[0]), int(xs[-1]) + 1)
        _BBOX[id(ov)] = box
        _KEEP[id(ov)] = ov
    y0, y1, x0, x1 = box
    a = ov[y0:y1, x0:x1, 3:4].astype(np.float32) * (opacity / 255.0)
    if not a.any():
        return canvas
    region = canvas[y0:y1, x0:x1].astype(np.float32)
    out = region * (1.0 - a) + ov[y0:y1, x0:x1, :3][:, :, ::-1].astype(np.float32) * a
    canvas[y0:y1, x0:x1] = out.astype(np.uint8)
    return canvas


def render(*, campaign: str, start: float, end: float, out: Path,
           transcript: Path, source: Path, font: str | None = None) -> dict:
    cdir = ROOT / "campaigns" / campaign
    rules = json.loads((cdir / "campaign_rules.json").read_text())
    style = json.loads((cdir / "style.json").read_text())
    if font:
        style["caption"] = font
    lex = TG.load_lexicon(cdir)
    data = json.loads(transcript.read_text())
    words = [w for w in data["words"] if start - 0.01 <= float(w["start"]) < end]

    # the campaign's own safety check, before a single frame is drawn
    hits = TG.scan_words(words, lexicon=lex)
    blocked = [h for h in hits if h["severity"] == "block"]
    if blocked:
        detail = ", ".join(f"{h['category']}:{h['term']}" for h in blocked[:4])
        raise SystemExit(f"blocked moment inside {start}-{end}s: {detail}")

    duration = end - start
    cards = build_cards(words, start=start, end=end)
    typer = FR.Typesetter(style)
    grade_cfg = {**{"curve": 0.26, "saturation": 1.05, "warmth": 0.010,
                    "cool": 0.008, "vignette": 0.10, "lift": 0.008,
                    "skin_guard": 0.55}, **(rules.get("grade") or {})}
    key_times = [c["at"] for card in cards for line in card["lines"] for c in line
                 if c["kind"] == "key"]
    punches: list[tuple[float, float]] = []
    last = -9.0
    for t in sorted(key_times):
        if t - last >= 0.9:
            punches.append((round(t, 3), 0.035))
            last = t

    brand = brand_layer(style, line1=str(rules.get("brand_line1", "2 BEARS 1 CAVE")),
                        line2=str(rules.get("brand_line2", "EP. 344")))

    # The opener is the clip's first sentence, not its first card: a card is
    # two words, and two words read as a fragment when they are the only thing
    # on screen. The same words, larger, hold the top of the frame while the
    # panel is still settling - and they are the caption's own words, so
    # nothing is claimed that is not said.
    hook_cells = _first_sentence(words, start, limit=8)
    hook_until = (float(hook_cells[-1]["end"]) - start + 0.45) if hook_cells else 0.0
    hook_until = min(3.4, max(1.1, hook_until)) if hook_cells else 0.0

    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    n = max(1, int(round(duration * fps)))

    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_name(out.stem + "_silent.mp4")
    enc = subprocess.Popen(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps:.3f}",
         "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)

    lay = LY.Layout()
    vig = None
    written = 0
    for i in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        panel = lay.panel_of(frame)
        if vig is None or vig.shape[:2] != panel.shape[:2]:
            vig = GR.mask_for(panel.shape, float(grade_cfg.get("vignette", 0.10)))
        panel = GR.apply(panel, grade_cfg, mask=vig)
        canvas = lay.compose_panel(panel, frame, slot=i)
        z = punch_at(t, punches)
        if z > 1.0005:
            canvas = MK.perspective_cam(canvas, zoom=min(1.08, z))
        canvas = blit(canvas, brand)
        hooked = bool(hook_cells) and t < hook_until
        if hooked:
            ov = typer.hook_image(hook_cells, t, y=120)
            fade = min(1.0, max(0.0, (hook_until - t) / 0.18))
            canvas = blit(canvas, ov, fade)
        for card in cards:
            # while the opener is up it *is* the caption, moved and enlarged;
            # printing the same words twice reads as a subtitle bug
            if hooked and card["show_from"] < hook_until:
                continue
            if card["show_from"] <= t < card["show_until"]:
                canvas = draw_caption(canvas, typer, card, t, duration=duration)
                break
        if t > duration - 0.4:
            canvas = (canvas.astype(np.float32)
                      * (1 - 0.9 * (t - (duration - 0.4)) / 0.4)).astype(np.uint8)
        enc.stdin.write(canvas.tobytes())
        written += 1
    cap.release()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("video encode failed")

    # ---- audio: same span, then voice, then bed
    wav = out.with_name(out.stem + "_a.m4a")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
                    "-vn", "-c:a", "aac", "-b:a", "192k", str(wav)], check=True)
    mixed = out.with_name(out.stem + "_mix.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(silent), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "copy", "-shortest", str(mixed)], check=True)
    VF.finish(mixed, {**VF.DEFAULT, **(rules.get("voice") or {})})

    # the bed is set from the *voice* level, so it has to be built after the
    # voice chain and before the final loudness settle
    intervals = [(float(w["start"]) - start, float(w["end"]) - start) for w in words]
    voice_rms = _speech_level(mixed)
    track = SD.build_track(duration, intervals, [t for t, _ in punches], 48000,
                           target_rms=SD.bed_target(voice_rms))
    SD.mix_into(mixed, out, track, 48000, ffmpeg())
    from tight_posts import settle_audio
    settle_audio(out, out)                       # -16 LUFS, -1.3 dBTP ceiling

    manifest = {
        "campaign": campaign, "title": None,
        "duration": round(duration, 3), "endcard": round(duration - 0.01, 3),
        "cards": [{"show_from": round(c["show_from"], 3),
                   "show_until": round(c["show_until"], 3),
                   "lines": [[x["w"] for x in line] for line in c["lines"]]} for c in cards],
        "words_kept": [{"w": c["w"], "at": round(c["at"], 3), "end": round(c["end"], 3)}
                       for card in cards for line in card["lines"] for c in line],
    }
    manifest_path = out.with_suffix(".cards.json")
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")

    for tmp in (silent, wav, mixed):
        tmp.unlink(missing_ok=True)
    return {"out": str(out), "frames": written, "duration": round(duration, 2),
            "cards": len(cards), "punches": len(punches),
            "manifest": str(manifest_path)}


def _speech_level(path: Path) -> float:
    """RMS of the voice as it now sounds, for the bed's ducking target."""
    from clipper.ffmpeg import decode_audio
    return SD.speech_level(decode_audio(path))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default="two_bears_ep344")
    ap.add_argument("--source", default="work/two_bears/full.mp4")
    ap.add_argument("--transcript", default="work/two_bears/asr/episode.json")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", help="override the style card's caption face")
    args = ap.parse_args()
    info = render(campaign=args.campaign, start=args.start, end=args.end,
                  out=Path(args.out), transcript=Path(args.transcript),
                  source=Path(args.source), font=args.font)
    print(json.dumps(info, indent=1))
    return 0


def punch_at(t: float, events: list[tuple[float, float]]) -> float:
    """Scale multiplier at t: 1.0 except on an emphasised word."""
    from tight_posts import punch_at as _pa
    return _pa(t, events)


if __name__ == "__main__":
    raise SystemExit(main())
