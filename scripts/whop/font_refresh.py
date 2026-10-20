#!/usr/bin/env python3
"""Font refresh: re-typeset a shipped Whop clip in the user's own fonts.

    .venv/bin/python scripts/whop/font_refresh.py post4

The shipped cuts for posts 4/6/7 were rendered before the user supplied
their own faces (now vendored in assets/fonts/). The clean source part
and its per-post transcript were never committed, so this pass works
from the shipped cut itself:

* the plan (scripts/whop/plans/postN.json) is still the verbatim
  caption text, with the same key-word emphasis;
* word timings are recovered from the shipped cut's own audio
  (Moonshine + energy alignment, work/street/postN/font_words.json);
* the old burned-in captions are ERASED (bright-stroke detection +
  inpainting, softened) and the caption is redrawn straight on the
  picture the old way - no matte panel, no black layer - in the
  user's Shawkind (all-caps display sans), key words in the post's accent;
* the full-screen hero (post6 "OAK TREE") and every end card
  ("FOLLOW FOR MORE") are redrawn full-frame in the user's Shawkind;
* everything else - the cut, the vector scenes, the music, the mix -
  is left frame-identical. Audio is copied untouched.

Scene/end-card windows below were measured off the shipped cuts
(frame brightness/texture steps), not guessed.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

W, H = 1080, 1920
FONTS = ROOT / "assets" / "fonts"
FLAVIOTTE = str(FONTS / "Flaviotte.ttf")
SHAWKIND = str(FONTS / "Shawkind.ttf")

# measured on the shipped cuts (brightness/texture steps + OCR)
WINDOWS = {
    "post4": {"endcard": 19.95},
    "post6": {"bigword": (2.18, 3.97), "endcard": 21.50},
    "post7": {"endcard": 20.38},
}
BAND = (1480, 1805)                     # burned-in caption band (y0, y1)
SCENE_BAND = (540, 740)                 # post6 oak-tree scene caption


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9']", "", tok.lower()).strip("'")


def _score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)):
        return 0.8
    return difflib.SequenceMatcher(None, a, b).ratio()


def build_captions(plan: dict, words: list[dict]) -> list[dict]:
    """Plan caption lines with a spoken time per word (sequential match)."""
    caps = []
    cursor = 0
    for beat in plan["beats"]:
        if beat.get("type") != "caption":
            continue
        kinds = beat.get("kinds") or []
        lines = []
        flat = []                       # (line_i, word_i) in reading order
        for li, line in enumerate(beat["lines"]):
            row = []
            for wi, tok in enumerate(line.split()):
                kind = "conn"
                if li < len(kinds) and wi < len(kinds[li]):
                    kind = kinds[li][wi]
                row.append({"w": tok, "kind": kind, "at": None, "end": None})
                flat.append((li, wi))
            lines.append(row)
        matched = []
        for li, wi in flat:
            cell = lines[li][wi]
            key = norm(cell["w"])
            best, best_j = 0.85, None
            for j in range(cursor, min(len(words), cursor + 9)):
                s = _score(key, norm(words[j]["text"]))
                if s > best:
                    best, best_j = s, j
                if best_j is not None and best >= 1.0:
                    break           # earliest exact hit wins
            if best_j is not None:
                cell["at"] = float(words[best_j]["start"])
                cell["end"] = float(words[best_j]["end"])
                cursor = best_j + 1
                matched.append(cell)
        if not matched:
            raise ValueError(f"no spoken match for caption {beat['lines']!r}")
        # unheard tokens (ASR drops) ride evenly between their neighbours
        cells = [lines[li][wi] for li, wi in flat]
        for i, cell in enumerate(cells):
            if cell["at"] is not None:
                continue
            prev = next((c for c in reversed(cells[:i]) if c["at"] is not None), None)
            nxt = next((c for c in cells[i:] if c["at"] is not None), None)
            if prev is not None and nxt is not None:
                span = max(nxt["at"] - prev["end"], 0.1)
                cell["at"] = prev["end"] + span * 0.4
                cell["end"] = prev["end"] + span * 0.7
            elif nxt is not None:
                cell["at"] = max(0.0, nxt["at"] - 0.16 * (len(cells) - i))
                cell["end"] = cell["at"] + 0.12
            else:
                cell["at"] = prev["end"] + 0.1
                cell["end"] = cell["at"] + 0.12
        caps.append({
            "zone": beat.get("zone", "low"),
            "lines": lines,
            "start": min(c["at"] for c in cells),
            "last_end": max(c["end"] for c in cells),
        })
    return caps


def caption_windows(caps: list[dict], endcard: float) -> None:
    for i, cap in enumerate(caps):
        nxt = caps[i + 1]["start"] if i + 1 < len(caps) else endcard
        cap["show_from"] = max(0.0, cap["start"] - 0.04)
        cap["show_until"] = min(nxt - 0.02, cap["last_end"] + 0.5, endcard)
    # the shipped captions held on screen through short pauses; if the
    # panel dropped out there, the old burned-in caption would flash
    # back in the old face for a few frames
    for i in range(len(caps) - 1):
        if 0 < caps[i + 1]["show_from"] - caps[i]["show_until"] < 0.75:
            caps[i]["show_until"] = caps[i + 1]["show_from"]


class Typesetter:
    def __init__(self, style: dict):
        colors = style["colors"]
        self.ink = hex_rgb(colors["caption"])
        self.accent = hex_rgb(colors["accent"])
        self.scene_bg = hex_rgb(colors["sceneBg"])
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._cache: dict[tuple, np.ndarray] = {}

    def font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        key = (path, size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(path, size)
        return self._fonts[key]

    # -- static full-frame plates ------------------------------------
    def endcard_image(self) -> np.ndarray:
        img = Image.new("RGB", (W, H), (11, 14, 17))
        d = ImageDraw.Draw(img)
        size = 170
        while size > 60:
            f = self.font(SHAWKIND, size)
            if max(d.textlength("FOLLOW", font=f),
                   d.textlength("FOR MORE", font=f)) <= 920:
                break
            size -= 6
        f = self.font(SHAWKIND, size)
        y = 790
        for line in ("FOLLOW", "FOR MORE"):
            tw = d.textlength(line, font=f)
            d.text(((W - tw) / 2, y), line, font=f, fill=self.accent)
            y += int(size * 1.12)
        d.rounded_rectangle((470, y + 30, 610, y + 42), radius=6,
                            fill=self.accent)
        return np.asarray(img)

    def bigword_image(self) -> np.ndarray:
        img = Image.new("RGB", (W, H), self.scene_bg)
        d = ImageDraw.Draw(img)
        size = 200
        while size > 60 and d.textlength("OAK TREE", font=self.font(SHAWKIND, size)) > 940:
            size -= 6
        f = self.font(SHAWKIND, size)
        tw = d.textlength("OAK TREE", font=f)
        d.text(((W - tw) / 2, 830), "OAK TREE", font=f, fill=(245, 243, 234))
        d.rounded_rectangle((150, 830 + size + 42, 930, 830 + size + 60),
                            radius=9, fill=self.accent)
        return np.asarray(img)

    # -- caption overlays (RGBA, text only - no plate) -----------------
    def _fit_size(self, cap: dict) -> int:
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        size = 84
        while size > 40:
            f = self.font(SHAWKIND, size)
            space = probe.textlength(" ", font=f)
            ok = True
            for line in cap["lines"]:
                width = sum(probe.textlength(c["w"], font=f)
                            + space for c in line) - space
                if width > 980:
                    ok = False
                    break
            if ok:
                return size
            size -= 2
        return size

    def overlay(self, cap: dict, t: float) -> np.ndarray:
        revealed = tuple(
            sum(1 for c in line if t >= c["at"] - 0.02) for line in cap["lines"])
        key = (id(cap), revealed)
        if key in self._cache:
            return self._cache[key]
        size = self._fit_size(cap)
        f = self.font(SHAWKIND, size)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        space = d.textlength(" ", font=f)

        def draw_word(x, y, cell):
            col = self.accent if cell["kind"] == "key" else self.ink
            d.text((x, y), cell["w"], font=f, fill=col + (255,),
                   stroke_width=3, stroke_fill=(0, 0, 0, 150))
            return d.textlength(cell["w"], font=f)

        if cap["zone"] == "scene":
            x = 64.0
            for ci, cell in enumerate(cap["lines"][0]):
                if ci >= revealed[0]:
                    break
                x += draw_word(x, 596, cell) + space
        else:
            advance = int(size * 1.26)
            total_h = advance * (len(cap["lines"]) - 1) + int(size * 0.86)
            y = 1652 - total_h / 2
            for li, line in enumerate(cap["lines"]):
                total = sum(d.textlength(c["w"], font=f) for c in line) \
                    + space * max(0, len(line) - 1)
                x = (W - total) / 2
                for ci, cell in enumerate(line):
                    if ci >= revealed[li]:
                        break
                    x += draw_word(x, y, cell) + space
                y += advance
        arr = np.asarray(img)
        self._cache[key] = arr
        return arr


def erase_captions(frame: np.ndarray, y0: int, y1: int) -> np.ndarray:
    """Remove burned-in caption strokes from a band of the frame.

    Captions are thin bright strokes over a much smoother picture, so a
    white top-hat finds them without touching skin or jacket. Inpaint,
    then soften the rebuilt patch so it reads as defocus, not a smear.
    """
    roi = frame[y0:y1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kern)
    mask = (top > 20).astype(np.uint8) * 255
    if not mask.any():
        return frame
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                      iterations=1)
    fixed = cv2.inpaint(roi, mask, 4, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(fixed, (0, 0), 2.2)
    a = cv2.GaussianBlur(mask, (0, 0), 2).astype(np.float32) / 255.0
    a = np.clip(a * 1.5, 0, 1)[:, :, None]
    out = frame.copy()
    out[y0:y1] = (fixed.astype(np.float32) * (1 - a)
                  + soft.astype(np.float32) * a).astype(np.uint8)
    return out


def ensure_words(post: str, src: Path) -> list[dict]:
    path = ROOT / "work" / "street" / post / "font_words.json"
    if path.exists():
        return json.loads(path.read_text())["words"]
    from clipper.asr.moonshine import MoonshineProvider
    from clipper.ffmpeg import decode_audio
    audio = decode_audio(src)
    tr = MoonshineProvider(chunk_seconds=6.0).transcribe(audio, 16000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tr.to_dict(), indent=1))
    return tr.to_dict()["words"]


def main() -> int:
    post = sys.argv[1]
    campaign = "street_you_grew_up_on"
    folder = ROOT / "campaigns" / campaign / post
    src = folder / f"street_{post}.mp4"
    plan = json.loads((ROOT / "scripts" / "whop" / "plans" / f"{post}.json").read_text())
    style = json.loads((folder / "style.json").read_text())
    assert style["caption"] == "shawkind" and style["endcard"] == "shawkind", \
        "style card is not on Shawkind yet"

    words = ensure_words(post, src)
    caps = build_captions(plan, words)
    win = WINDOWS[post]
    endcard_at = win["endcard"]
    caption_windows(caps, endcard_at)
    for cap in caps:
        print(f"  {cap['show_from']:5.2f}-{cap['show_until']:5.2f}  "
              + " / ".join(" ".join(c['w'] for c in line) for line in cap['lines']))

    cap_v = cv2.VideoCapture(str(src))
    fps = cap_v.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap_v.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = n_frames / fps
    typer = Typesetter(style)
    endcard_img = typer.endcard_image()
    bigword_img = typer.bigword_image() if "bigword" in win else None

    out_path = ROOT / "work" / "street" / post / "font_refresh_video.mp4"
    ff = subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()
    mux_path = ROOT / "work" / "street" / post / "font_refresh.mp4"
    enc = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", f"{fps:.3f}", "-i", "-",
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out_path)],
        stdin=subprocess.PIPE)

    def active_cap(t: float):
        for cap in caps:
            if cap["show_from"] <= t < cap["show_until"]:
                return cap
        return None

    for fi in range(n_frames):
        ok, frame = cap_v.read()
        if not ok:
            break
        t = fi / fps
        if t >= endcard_at:
            frame = cv2.cvtColor(endcard_img, cv2.COLOR_RGB2BGR)
        elif bigword_img is not None and win["bigword"][0] <= t < win["bigword"][1]:
            frame = cv2.cvtColor(bigword_img, cv2.COLOR_RGB2BGR)
        cap = active_cap(t)
        if cap is not None and t < endcard_at:
            band = SCENE_BAND if cap["zone"] == "scene" else BAND
            frame = erase_captions(frame, *band)
            ov = typer.overlay(cap, t)
            alpha = ov[:, :, 3:4].astype(np.float32) / 255.0
            if alpha.any():
                frame = (frame.astype(np.float32) * (1 - alpha)
                         + ov[:, :, :3][:, :, ::-1].astype(np.float32) * alpha
                         ).astype(np.uint8)
        if t > duration - 0.5:                      # keep the shipped fade-out
            frame = (frame.astype(np.float32)
                     * (1 - 0.92 * (t - (duration - 0.5)) / 0.5)).astype(np.uint8)
        enc.stdin.write(frame.tobytes())
    cap_v.release()
    enc.stdin.close()
    enc.wait()
    if enc.returncode != 0:
        raise SystemExit("encode failed")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(out_path), "-i", str(src),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                    "-shortest", str(mux_path)], check=True)
    dest = folder / f"street_{post}.mp4"
    dest.write_bytes(mux_path.read_bytes())
    print(f"shipped {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
