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

import os

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR      # noqa: E402
import grade_fast as GR         # noqa: E402
import reframe as RF            # noqa: E402
import font_refresh as FR       # noqa: E402
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


def is_key(text: str, emphasis: list[str] | None = None) -> bool:
    """Is this word set in the emphasis ink at 1.16x?

    Three sources, in order: the clip's own emphasis list (chosen by whoever
    picked the moment - the street campaign worked the same way, with the key
    words named per post), then a small list of absolutes, then a number.
    """
    t = str(text).strip().lower().strip(".,!?\"'")
    if emphasis:
        return any(t == str(e).strip().lower().strip(".,!?\"'") or
                   t.startswith(str(e).strip().lower().strip(".,!?\"'") + ",")
                   for e in emphasis)
    return bool(EMPHASIS.match(t)) or bool(re.search(r"\d", t))


def build_cards(words: list[dict], *, start: float, end: float,
                max_chars: int = CR.MAX_LINE_CHARS,
                emphasis: list[str] | None = None) -> list[dict]:
    """Cells -> short-line cards, timed from the words themselves."""
    cells = [{"w": w["text"], "at": float(w["start"]) - start,
              "end": float(w["end"]) - start,
              "kind": "key" if is_key(w["text"], emphasis) else "conn"}
             for w in words if start <= float(w["start"]) < end]
    if not cells:
        return []
    cards: list[dict] = []
    for card in CR.wrap_cells(cells, max_chars):
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
    return blit(canvas, ov, shift=shift)


_BBOX: dict[int, tuple[int, int, int, int]] = {}
_KEEP: dict[int, np.ndarray] = {}        # keep the keyed layer alive: ids are reused


def _first_sentence(words: list[dict], start: float, *, limit: int = 6,
                    emphasis: list[str] | None = None) -> list[dict]:
    """The opening words, up to the first full stop and at most `limit` long."""
    out: list[dict] = []
    for w in words:
        if float(w["start"]) < start - 0.01:
            continue
        out.append({"w": w["text"], "at": float(w["start"]) - start,
                    "end": float(w["end"]) - start,
                    "kind": "key" if is_key(w["text"], emphasis) else "conn"})
        if len(out) >= limit or str(w["text"]).rstrip('"\')').endswith((".", "?", "!")):
            break
    return out


def bug_layer(style: dict, *, line: str) -> np.ndarray:
    """The show bug: one small line at the top, for the whole clip.

    It is the payout mention, made visible: a viewer who screenshots the clip
    can still find the show and the episode from the picture alone. Set small
    and high on purpose - a title-sized credit at the top of a full-bleed crop
    competes with the kinetic open, which is the thing that has to land first.
    """
    from PIL import Image, ImageDraw, ImageFont
    ink = FR.hex_rgb(style["colors"]["accent"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FR.font_path(style.get("caption") or style.get("font")), 46)
    tw = d.textlength(line, font=f)
    x, y = (W - tw) / 2, 54
    d.text((x, y), line, font=f, fill=ink + (255,),
           stroke_width=3, stroke_fill=(0, 0, 0, 150))
    return np.asarray(img)


def endcard_layer(style: dict, *, head: str, sub: str, tail: str) -> np.ndarray:
    """The card the clip ends on, instead of ending on the peak.

    Same three jobs as the street posts' end card: name the show and episode,
    say where the rest is, and give the eye somewhere to land at the cut - a
    clip that stops mid-expression reads as broken, one that stops on a card
    reads as finished.
    """
    from PIL import Image, ImageDraw, ImageFont
    ink = FR.hex_rgb(style["colors"]["endcard"])
    paper = FR.hex_rgb(style["colors"].get("listBg") or "#141414")
    white = FR.hex_rgb(style["colors"]["caption"])
    face = FR.font_path(style.get("endcard") or style.get("caption") or style.get("font"))
    img = Image.new("RGBA", (W, H), paper + (255,))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(face, 132)
    f2 = ImageFont.truetype(face, 66)
    f3 = ImageFont.truetype(face, 46)
    y = 700
    for text, font, fill in ((head, f1, ink), (sub, f2, white), (tail, f3, white)):
        tw = d.textlength(text, font=font)
        d.text(((W - tw) / 2, y), text, font=font, fill=fill)
        y += int(font.size * 1.5)
    d.rectangle((W // 2 - 70, y + 40, W // 2 + 70, y + 52), fill=ink + (255,))
    return np.asarray(img)


def _fade_rgba(layer: np.ndarray, opacity: float) -> np.ndarray:
    out = layer.copy()
    out[:, :, 3] = (out[:, :, 3].astype(np.float32) * opacity).astype(np.uint8)
    return out


def zoom_canvas(img: np.ndarray, z: float) -> np.ndarray:
    """Scale about the centre without resampling the whole frame twice."""
    if z <= 1.0005:
        return img
    h, w = img.shape[:2]
    nw, nh = max(1, int(round(w / z))), max(1, int(round(h / z)))
    x0, y0 = (w - nw) // 2, (nh - h) // 2 + (h - nh) // 2
    y0 = (h - nh) // 2
    crop = img[y0:y0 + nh, x0:x0 + nw]
    return cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)


def blit(canvas: np.ndarray, ov: np.ndarray, opacity: float = 1.0,
         shift: int = 0) -> np.ndarray:
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
    if shift:
        # the drift is applied to the layer's own box, not to the frame: a
        # rolled copy of a full 1080x1920 RGBA layer is 8 MB a frame, and
        # caching its box (as this function does) made that permanent - which
        # is what filled the box's memory the first time this ran long.
        x0 = max(0, x0 - abs(shift))
        x1 = min(canvas.shape[1], x1 + abs(shift))
    layer = ov[y0:y1, x0:x1]
    if shift:
        layer = np.roll(layer, shift, axis=1)
    a = layer[:, :, 3:4].astype(np.float32) * (opacity / 255.0)
    if not a.any():
        return canvas
    region = canvas[y0:y1, x0:x1].astype(np.float32)
    out = region * (1.0 - a) + layer[:, :, :3][:, :, ::-1].astype(np.float32) * a
    canvas[y0:y1, x0:x1] = out.astype(np.uint8)
    return canvas


def render(*, campaign: str, start: float, end: float, out: Path,
           transcript: Path, source: Path, font: str | None = None,
           emphasis: list[str] | None = None,
           endcard: float = 1.4) -> dict:
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
    cards = build_cards(words, start=start, end=end,
                        max_chars=int((rules.get("caption_rules") or {})
                                      .get("max_chars_per_line", CR.MAX_LINE_CHARS)),
                        emphasis=emphasis)
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

    bug = bug_layer(style, line=str(rules.get("bug_line", "2 BEARS 1 CAVE  ·  EP. 344")))
    card = endcard_layer(style,
                         head=str(rules.get("endcard_head", "2 BEARS")),
                         sub=str(rules.get("endcard_sub", "1 CAVE  ·  EP. 344")),
                         tail=str(rules.get("endcard_tail", "Full episode in bio")))

    # The opener is the clip's first sentence, set in kinetic type: each word
    # springs in on its own beat, key words in the emphasis ink. It is the
    # caption's own words, so nothing is claimed that is not said - and it is
    # the first thing a muted autoplay viewer reads.
    hook_cells = _first_sentence(words, start, limit=6, emphasis=emphasis)
    # hook_cells carry times already relative to the cut (see _first_sentence);
    # subtracting `start` again here collapsed the window to its 1.3 s floor and
    # the kinetic open never appeared.
    hook_until = (float(hook_cells[-1]["end"]) + 0.55) if hook_cells else 0.0
    hook_until = min(3.6, max(1.3, hook_until)) if hook_cells else 0.0
    kin_words = [(c["w"], c["kind"] == "key") for c in hook_cells]
    kin_ink = tuple(reversed(FR.hex_rgb(style["colors"]["caption"])))      # BGR
    kin_key = tuple(reversed(FR.hex_rgb(style["colors"].get("keyword")
                                        or style["colors"]["accent"])))
    card_h = max(0.6, float(endcard))
    body = max(0.5, duration - card_h)

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

    # The 9:16 window follows the face. `Reframe` reports a cut when the
    # subject really changes; that is where the whip fires, because a cut with
    # no transition is the thing that reads as a glitch.
    slug = out.stem
    rf = RF.Reframe()
    vig = GR.mask_for((H, W), float(grade_cfg.get("vignette", 0.10)))
    ramp = rules.get("ramp") or {}
    ramp_on = bool(ramp.get("enabled", True)) and not bool(ramp.get("disabled"))
    ramp_window = float(ramp.get("window", 1.1))
    whip_start = -1.0
    whip_dir = 1
    written = 0

    for i in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        x0, cut = rf.crop_x(frame, t)
        if cut and i > 2:
            whip_start = t
            whip_dir = -whip_dir
        canvas = rf.apply(frame, x0=x0)
        canvas = GR.apply(canvas, grade_cfg, mask=vig)

        # slow push for the whole clip + a punch on each emphasised word:
        # one scale, computed per frame, so the two never fight
        z = 1.0
        if ramp_on:
            z *= 1.0 + 0.045 * min(1.0, t / max(ramp_window, 0.01))
        z = max(z, punch_at(t, punches))
        canvas = zoom_canvas(canvas, z)

        # A whip is a smeared frame at the seam, not a permanent offset: the
        # envelope rises and falls inside 0.18 s, so it reads as speed. It is
        # applied to the *picture* only - smearing the caption and the bug with
        # it turns a transition into what looks like a broken render (words
        # doubled, the credit half off the top). Applied to the end card it
        # would smear the credit, so it stops at the card.
        if whip_start >= 0 and t < body and 0.0 <= t - whip_start <= 0.18:
            u = (t - whip_start) / 0.18
            canvas = MK.whip_pan(canvas, 0.55 * math.sin(math.pi * u),
                                 direction=whip_dir)

        if i % 60 == 0:
            typer._cache.clear()
            _BBOX.clear()
            _KEEP.clear()

        if t < body:
            hooked = bool(kin_words) and t < hook_until
            if hooked:
                canvas = MK.kinetic_type(
                    canvas, kin_words, t, t0=0.0, font_path=typer.face,
                    ink=kin_ink, key_ink=kin_key, size=120, gap=0.13,
                    y=1560, line_h=150, per_line=2, settle_rot=-3.0)
            for c in cards:
                # while the kinetic open is up it *is* the caption: a second set
                # of subtitles underneath the same words reads as a bug
                if hooked:
                    break
                if c["show_from"] <= t < c["show_until"]:
                    canvas = draw_caption(canvas, typer, c, t, duration=duration)
                    break
            canvas = blit(canvas, bug)

        if t >= body:
            # the card, eased in over 0.22 s so it reads as an ending
            a = min(1.0, (t - body) / 0.22)
            ov = card if a >= 1.0 else _fade_rgba(card, a)
            canvas = blit(canvas, ov)

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
    under = (rules.get("bed") or {})
    under = float(under.get("under_voice_db", 19.5)) if isinstance(under, dict) else 19.5
    track = SD.build_track(duration, intervals, [t for t, _ in punches], 48000,
                           target_rms=SD.bed_target(voice_rms, under_db=under))

    # Keyboard typing on the caption reveal grid - the house sound from the
    # street campaign: real recorded keys, one short burst per word, gated to
    # the caption windows so there is silence before the first word and over
    # the end card. A whoosh lands on each whip, because a whip with no sound
    # is a smear rather than a cut.
    import keyboard_sfx as KB
    keys, key_log = KB.typing_track(cards, duration, body, slug)
    track, key_gain = KB.mix_into(track, keys)
    track = _add_whooshes(track, rf.cuts, 48000)
    SD.mix_into(mixed, out, track, 48000, ffmpeg())
    from tight_posts import settle_audio
    settle_audio(out, out)                       # -16 LUFS, -1.3 dBTP ceiling

    manifest = {
        "campaign": campaign, "title": None,
        "duration": round(duration, 3), "endcard": round(body, 3),
        "emphasis": list(emphasis or []),
        "cuts": [round(float(c), 2) for c in rf.cuts],
        "features": _features(cards, punches, kin_words, key_log, rf.cuts),
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


def _features(cards: list[dict], punches: list[tuple[float, float]],
              kin_words: list[tuple[str, bool]], key_log: list[dict],
              cuts: list[float]) -> list[str]:
    """What this render actually did, for skill_gate to check against the
    campaign's contract. Only claims a feature when it really ran."""
    has_key = any(c["kind"] == "key" for card in cards
                  for line in card["lines"] for c in line)
    feats = ["reframe_9x16", "endcard", "bug", "grade", "bed", "voice"]
    if kin_words:
        feats.append("kinetic_type")
    if has_key:
        feats.append("emphasis_ink")
    if punches:
        feats.append("punch")
    feats.append("ramp")
    feats.append("whip")
    if key_log:
        feats.append("keyboard_sfx")
    if any(c > 0.35 for c in cuts):
        feats.append("whoosh_sfx")
    return feats


def _add_whooshes(track: np.ndarray, cuts: list[float], rate: int = 48000,
                  gain: float = 0.30) -> np.ndarray:
    """A recorded whoosh on every cut, under the bed, not over the voice."""
    wav = ROOT / "assets" / "sfx" / "whoosh.wav"
    if not cuts or not wav.exists():
        return track
    from clipper.ffmpeg import decode_audio
    shot = decode_audio(str(wav), rate=rate)
    shot = (np.asarray(shot, dtype=np.float32).reshape(-1) * gain)
    out = track.copy()
    while shot.ndim > 1:
        shot = shot.mean(axis=1)
    for t in cuts:
        if t < 0.35:            # the first frame is a "cut" only by definition
            continue
        i = int(max(0.0, t - 0.05) * rate)
        j = min(len(out), i + len(shot))
        if j > i:
            out[i:j] += shot[: j - i, None]
    return out


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
