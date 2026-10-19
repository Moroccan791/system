#!/usr/bin/env python3
"""Font refresh: re-typeset a shipped Whop clip in the user's own fonts.

    .venv/bin/python scripts/whop/font_refresh.py post4

The shipped cuts for posts 4/6/7 were rendered before the user supplied
their own faces (Cabinet Grotesk + Jasper, now vendored in
assets/fonts/). The clean source part and its per-post transcript were
never committed, so this pass works from the shipped cut itself:

* the plan (scripts/whop/plans/postN.json) is still the verbatim
  caption text, with the same key-word emphasis;
* word timings are recovered from the shipped cut's own audio
  (Moonshine + energy alignment, work/street/postN/font_words.json);
* the old burned-in caption band is covered by one flat editorial
  matte panel and the caption is redrawn in Cabinet Grotesk
  (Medium for connective words, Bold in the post's accent for keys);
* the full-screen hero (post6 "OAK TREE") and every end card
  ("FOLLOW FOR MORE") are redrawn full-frame in Jasper;
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
CAB_M = str(FONTS / "CabinetGrotesk-Medium.otf")
CAB_B = str(FONTS / "CabinetGrotesk-Bold.otf")
JASPER = str(FONTS / "Jasper.otf")

# measured on the shipped cuts (brightness/texture steps + OCR)
WINDOWS = {
    "post4": {"endcard": 19.95},
    "post6": {"bigword": (2.18, 3.97), "endcard": 21.50},
    "post7": {"endcard": 20.38},
}
PANEL = (58, 1496, 1022, 1794)          # x0, y0, x1, y1
SCENE_COVER = (0, 545, 1080, 735)       # post6 oak-tree scene caption


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
        size = 150
        while size > 60:
            f = self.font(JASPER, size)
            if max(d.textlength("FOLLOW", font=f),
                   d.textlength("FOR MORE", font=f)) <= 900:
                break
            size -= 6
        f = self.font(JASPER, size)
        y = 800
        for line in ("FOLLOW", "FOR MORE"):
            tw = d.textlength(line, font=f)
            d.text(((W - tw) / 2, y), line, font=f, fill=self.accent)
            y += int(size * 1.18)
        d.rounded_rectangle((470, y + 26, 610, y + 38), radius=6,
                            fill=self.accent)
        return np.asarray(img)

    def bigword_image(self) -> np.ndarray:
        img = Image.new("RGB", (W, H), self.scene_bg)
        d = ImageDraw.Draw(img)
        size = 190
        while size > 60 and d.textlength("OAK TREE", font=self.font(JASPER, size)) > 920:
            size -= 6
        f = self.font(JASPER, size)
        tw = d.textlength("OAK TREE", font=f)
        d.text(((W - tw) / 2, 830), "OAK TREE", font=f, fill=(245, 243, 234))
        d.rounded_rectangle((150, 830 + size + 42, 930, 830 + size + 60),
                            radius=9, fill=self.accent)
        return np.asarray(img)

    # -- caption overlays (RGBA) --------------------------------------
    def _fit_size(self, cap: dict) -> int:
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        size = 62
        while size > 42:
            fm, fb = self.font(CAB_M, size), self.font(CAB_B, size)
            space = probe.textlength(" ", font=fm)
            ok = True
            for line in cap["lines"]:
                width = sum(probe.textlength(c["w"], font=fb if c["kind"] == "key" else fm)
                            + space for c in line) - space
                if width > 884:
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
        fm, fb = self.font(CAB_M, size), self.font(CAB_B, size)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if cap["zone"] == "scene":
            x0, y0, x1, y1 = SCENE_COVER
            d.rectangle((x0, y0, x1, y1), fill=self.scene_bg + (255,))
            line = cap["lines"][0]
            space = d.textlength(" ", font=fm)
            x = 64.0
            for ci, cell in enumerate(line):
                if ci >= revealed[0]:
                    break
                f = fb if cell["kind"] == "key" else fm
                col = self.accent if cell["kind"] == "key" else self.ink
                d.text((x, 596), cell["w"], font=f, fill=col + (255,))
                x += d.textlength(cell["w"], font=f) + space
        else:
            x0, y0, x1, y1 = PANEL
            # fully opaque: a translucent matte lets the old burned-in
            # white caption ghost through at phone brightness
            d.rounded_rectangle((x0, y0, x1, y1), radius=28,
                                fill=(13, 16, 19, 255))
            d.rounded_rectangle((x0 + 38, y0 + 22, x1 - 38, y0 + 30),
                                radius=4, fill=self.accent + (255,))
            advance = int(size * 1.34)
            block_h = advance * len(cap["lines"]) - int(size * 0.34)
            y = (y0 + y1) / 2 - block_h / 2 + 10
            space = d.textlength(" ", font=fm)
            for li, line in enumerate(cap["lines"]):
                widths = [d.textlength(c["w"], font=fb if c["kind"] == "key" else fm)
                          for c in line]
                total = sum(widths) + space * max(0, len(line) - 1)
                x = (W - total) / 2
                for ci, cell in enumerate(line):
                    if ci >= revealed[li]:
                        break
                    f = fb if cell["kind"] == "key" else fm
                    col = self.accent if cell["kind"] == "key" else self.ink
                    d.text((x, y), cell["w"], font=f, fill=col + (255,))
                    x += widths[ci] + space
                y += advance
        arr = np.asarray(img)
        self._cache[key] = arr
        return arr


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
    assert style["caption"] == "cabinet" and style["endcard"] == "jasper", \
        "style card is not on the user's fonts yet"

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
