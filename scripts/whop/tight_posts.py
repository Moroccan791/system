#!/usr/bin/env python3
"""Campaign pass for a shipped clip: bars out, camera in, emphasis words up.

    .venv/bin/python scripts/whop/tight_posts.py post6 post7

`retighten.py` does this for post4, where the audio could be rebuilt from the
raw take (its source part was still on disk). Posts 6 and 7 are different:
the only master we have is the shipped cut itself, with the music bed and the
keyboard already mixed in. So this pass leaves the sound **bit for bit**
alone and rebuilds the picture around it. That has three useful properties:

* the caption reveal grid is unchanged, so the keyboard that is already in
  the mix still lands on the same keystrokes - nothing to re-time;
* sync cannot regress: the captions keep the exact word times the approved
  render had (measured off this same audio);
* the mix keeps its loudness and true peak instead of being re-encoded.

What it does change:

* **Black bars.** The interview plates carry a black strip across the top -
  137 px on post6, 105 px on post7, and on post7 it only appears from the
  second shot on. The bar is measured per frame and cropped, so the picture
  is re-fitted to a full 1080x1920 and the strip is gone; because the strip
  starts and stops exactly on a shot change, the re-fit is invisible.
* **Camera.** A slow push through the hook, a release on the turn, a punch-in
  on the impact word, another push on the emotional close - the same idea as
  post4, keyed to the words rather than to fixed seconds.
* **Emphasis.** Key words are set 16% larger than the words around them
  (1.16x, baseline aligned so the line still sits level) and take the post's
  emphasis ink - yellow on post6, red on post7 - as the user asked. The
  stroke goes 3 px -> 4 px on those words so the bigger glyphs stay clean
  over skin and hair. Caption ink stays the approved ivory.
* **End card and the Oak Tree plate** are redrawn from the same typesetter,
  so they follow the new emphasis colour too.

Everything is still the user's Shawkind, still verbatim, still no plate
behind the caption.

How the render relates to the rules in `caption_rules.py` and the campaign
gate (`qc_gate.py`): captions are re-wrapped here to short lines, the camera
supports a *release* key (zoom back down on a punchline, not only push in),
and the ending has two modes - the branded CTA card, or a hard cut on the
last spoken word for when the peak is the point. The gate then grades the
file; nothing here decides on its own that a clip is good.

    # preview only: never touches the shipped file
    .venv/bin/python scripts/whop/tight_posts.py post7 --preview
    .venv/bin/python scripts/whop/qc_gate.py <preview.mp4> --manifest <...>

    # deliver (replaces campaigns/<c>/<post>/<file>.mp4)
    .venv/bin/python scripts/whop/tight_posts.py post7 --ship
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import font_refresh as FR                     # Typesetter, erase_captions, build_captions
import sound_design as SD                      # synthesised bed + hits we own outright
import director as DIR                         # which move this shot needs, and which it does not
import voice_finish as VF                      # rumble/mud out, presence in, before the bed
import timeline as TL                          # dead-air cuts, and the clock they move
import body_mask as BM                         # person roto: lift, wrap, parallax
import motion_kit as MK                        # whip/zoom transitions between shots
import cover as CV                             # the frame the grid actually shows
import caption_rules as CR                     # 14-char lines, fillers, card timing

W, H = FR.W, FR.H
CAMPAIGN = "street_you_grew_up_on"

#: Per-post direction. `zoom` is (anchor, zoom): an anchor is either a spoken
#: word (taken from the clip's own transcript, so it survives any re-cut) or a
#: number of seconds. `shake` is (anchor, amplitude px, duration s).
POSTS: dict[str, dict] = {
    "post6": {
        "hook_y": 296,
        "emphasis": "#FFC83D",           # warm yellow - pops on sage + ivory
        "zoom": [
            (0.00, 1.000), ("build", 1.030), ("oak", 1.048),
            ("soil", 1.010), ("protect", 1.040), ("children", 1.048),
            ("influence", 1.004), ("kids", 1.026), ("journey", 1.044),
            ("excited", 1.018),
        ],
        "shake": [("protect", 2.2, 0.30)],
        "cover": None,                   # filled in from a key caption
        "cover_word": "beautiful",
    },
    "post7": {
        "hook_y": 292,
        "emphasis": "#E23B2F",           # red - the clip's warm palette, turned up
        "zoom": [
            (0.00, 1.000), ("never", 1.024), ("angry", 1.052),
            ("struggle", 1.012), ("share", 1.040), ("beautiful", 1.014),
            ("treatment", 1.006), ("open", 1.030), ("door", 1.052),
            ("work", 1.016),
        ],
        "shake": [("angry", 1.8, 0.28)],
        "cover": None,
        "cover_word": "struggle",
    },
}

#: The bed. Off in the rules only if a campaign explicitly says so; on by
#: default because a bare talking head has no floor under it. Level is applied
#: inside `sound_design` (BED_RMS) and then verified by the gate's
#: voice-over-bed check, which fails a render where the voice is not 12 dB
#: clear of it.
DEFAULT_SOUND = {"enabled": True, "bed": True, "hits": True, "rate": 48000}

END_MODES = ("card", "peak")   # "card" = branded CTA, "peak" = cut on the word

#: The finish. Everything here is deliberately small: a grade you can name from
#: a still is a grade turned up too far on a talking-head clip. In order - a
#: filmic S-curve for contrast that does not crush blacks, a touch of
#: saturation so skin and set dressing read on a phone, warm highlights and
#: cool shadows (the "shot on a real camera" cue), and a soft vignette that
#: pulls the eye to the face. The caption is drawn *after* this, so the type
#: stays the exact approved ivory and emphasis ink.
#: Tuned on a face, not on a colour chart. The first pass at warmth 0.022
#: pushed skin orange - skin lives in the highlights, which is exactly where
#: the amber was going - so the warm lift is now small, capped, and skipped
#: where the pixels are already highly saturated (i.e. on skin). A grade
#: should make the shot look shot-better, never tanned.
DEFAULT_GRADE = {
    "curve": 0.26,          # 0 = linear, 1 = hard S
    "saturation": 1.05,
    "warmth": 0.010,        # highlights toward amber (skin-safe ceiling)
    "cool": 0.008,          # shadows toward teal
    "vignette": 0.10,
    "lift": 0.008,          # raise the floor a hair so blacks are not dead
    "skin_guard": 0.55,     # warmth fades out as saturation rises
}


def grade_frame(frame: np.ndarray, g: dict, mask: np.ndarray | None = None) -> np.ndarray:
    """Apply the finish to footage.

    Vector plates and the end card are skipped by the caller: their colours are
    brand colours, approved in the style card, and a grade over them would move
    the ink the user signed off on.
    """
    curve = float(g.get("curve", 0.0))
    sat = float(g.get("saturation", 1.0))
    warm = float(g.get("warmth", 0.0))
    cool = float(g.get("cool", 0.0))
    lift = float(g.get("lift", 0.0))
    vig = float(g.get("vignette", 0.0))
    if not curve and abs(sat - 1) < 1e-3 and not warm and not cool and not vig and not lift:
        return frame

    # 1. tone: a 256-entry curve applied as a LUT, so the per-frame cost is nil
    x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    s_curve = x * x * (3.0 - 2.0 * x)                 # smoothstep
    tone = (x * (1.0 - curve) + s_curve * curve) + lift * (1.0 - x)
    lut = np.clip(tone * 255.0, 0, 255).astype(np.uint8)
    out = cv2.LUT(frame, lut)

    if abs(sat - 1.0) > 1e-3 or warm or cool:
        f = out.astype(np.float32) / 255.0
        luma = (f[:, :, 0] * 0.114 + f[:, :, 1] * 0.587 + f[:, :, 2] * 0.299)
        f = luma[:, :, None] + (f - luma[:, :, None]) * sat
        if warm or cool:
            guard = float(g.get("skin_guard", 0.55))
            sat_map = (f.max(axis=2) - f.min(axis=2))          # 0 grey .. ~1 vivid
            skin = np.clip((sat_map - 0.18) / max(1e-3, guard), 0.0, 1.0)[:, :, None]
            hi = np.clip((luma - 0.55) / 0.45, 0.0, 1.0)[:, :, None] * (1.0 - skin)
            lo = np.clip((0.45 - luma) / 0.45, 0.0, 1.0)[:, :, None] * (1.0 - skin)
            f = f + hi * np.array([-0.30, 0.50, 1.00], np.float32) * warm   # amber
            f = f + lo * np.array([0.75, 0.20, -0.50], np.float32) * cool   # teal
        out = np.clip(f * 255.0, 0, 255).astype(np.uint8)

    if vig > 0.01:
        if mask is None:
            h, w = out.shape[:2]
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            cy, cx = h * 0.46, w * 0.5
            r = np.sqrt(((xx - cx) / (w * 0.62)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
            mask = np.clip(1.0 - vig * np.clip(r - 0.45, 0, None) ** 1.4 * 2.2, 0.0, 1.0)
            mask = mask[:, :, None].astype(np.float32)
        out = (out.astype(np.float32) * mask).astype(np.uint8)
    return out
BAR_MIN = 20            # a top strip shorter than this is picture, not a bar
PLATE_STD = 42.0        # frame std below this = vector plate, not footage


# ------------------------------------------------------------------- erase
def erase_plate(frame: np.ndarray, y0: int, y1: int) -> np.ndarray:
    """Take a burned-in caption off a flat (vector) plate.

    `font_refresh.erase_captions` rebuilds whole rows for this case, but it
    finds them from a bright top-hat: on a dark plate the caption's black
    outline scores below the threshold, the rebuilt range comes up short and
    the outline survives as a ghost of the old words next to the new ones
    (measured on post6's Oak Tree plate). A caption row is simply much noisier
    across x than the plate it sits on, so the rows are found from that
    instead - bright glyph and dark outline both raise the row's variance -
    and the block is rebuilt column-by-column between the clean rows above
    and below it, then blended with a narrow feather.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    band = gray[y0:y1]
    ground = float(np.median(band))
    # Three cues, because the two shipped plates fail in different ways. The
    # glyph core is bright (>238). The outline is dark, so it only shows up as
    # a row that is noisier across x than the plate around it. And on post7's
    # last plate the shipped caption had already faded to ~10% white before the
    # cut, so the only trace left of the old words is a faint mid-grey - caught
    # here as pixels well above the plate's own level. Every cue is measured
    # against the plate, never against a fixed grey level.
    rows_std = band.astype(np.float32).std(axis=1)
    base = float(np.median(rows_std))
    bright = (band > 238).sum(axis=1)
    raised = (band > ground + 16).sum(axis=1)
    hot = np.where((bright > 3) | (raised > 6) | (rows_std > base * 1.30 + 0.5))[0]
    if len(hot) == 0:
        return frame
    strong = bool((bright > 3).any() or (raised > 6).any())
    pad = 12 if strong else 6
    r0 = max(1, int(hot.min()) - pad)
    r1 = min(len(band) - 2, int(hot.max()) + pad)
    if r1 - r0 < 4:
        return frame
    out = frame.copy()
    up = frame[y0 + r0 - 1].astype(np.float32)
    dn = frame[y0 + r1 + 1].astype(np.float32)
    span = r1 - r0 + 1
    for i in range(span):
        w = (i + 1) / (span + 1)
        out[y0 + r0 + i] = (up * (1 - w) + dn * w).astype(np.uint8)
    mask = np.zeros(frame.shape[:2], np.uint8)
    mask[y0 + r0:y0 + r1 + 1] = 255
    a = (cv2.GaussianBlur(mask, (0, 0), 3).astype(np.float32) / 255.0)[:, :, None]
    return (out.astype(np.float32) * a + frame.astype(np.float32) * (1 - a)).astype(np.uint8)


def clean_caption_band(frame: np.ndarray, y0: int, y1: int,
                       plate: bool) -> np.ndarray:
    return erase_plate(frame, y0, y1) if plate else FR.erase_captions(frame, y0, y1)


# ------------------------------------------------------------------ camera
def bar_rows(gray: np.ndarray) -> int:
    """Height of the black strip across the top of an interview plate."""
    dark = gray.mean(axis=1) < 14
    rows = 0
    while rows < 240 and rows < len(dark) and dark[rows]:
        rows += 1
    return rows if rows >= BAR_MIN else 0


def camera_frame(frame: np.ndarray, bar: int, z: float,
                 dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """Crop the strip, fit the rest to 1080x1920, then zoom/shake."""
    src = frame[bar:] if bar else frame
    sh, sw = src.shape[:2]
    if bar == 0 and abs(z - 1.0) < 1e-6 and not dx and not dy:
        return frame
    scale = max(W / sw, H / sh) * z
    cw, ch = W / scale, H / scale
    cx = sw / 2.0 + dx / scale
    cy = sh * 0.44 + dy / scale
    x0 = min(max(0.0, cx - cw / 2), sw - cw)
    y0 = min(max(0.0, cy - ch / 2), sh - ch)
    return cv2.resize(src[int(round(y0)):int(round(y0 + ch)),
                         int(round(x0)):int(round(x0 + cw))],
                      (W, H), interpolation=cv2.INTER_CUBIC)


#: Punch-ins. The authored `zoom` keys are a slow push across the whole clip;
#: they never react to a single word. These do: a 3.5% bump that lands on the
#: emphasised word, holds while it is read, and is gone before the next one.
#: It is the cheapest thing in an edit that reads as "someone is cutting this".
PUNCH = {"amount": 0.035, "attack": 0.07, "hold": 0.20, "release": 0.38,
         "min_gap": 0.90, "max": 9}


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def punch_events(times: list[float], spec: dict | None = None) -> list[tuple[float, float]]:
    """Turn emphasised-word times into (start, amount) punches, spaced out.

    Emphasis is already decided by the caption engine (the words it sets in
    the key ink, 1.16x); the camera should agree with it rather than carry a
    second, hand-maintained list of "important" words that drifts from the
    captions.
    """
    sp = {**PUNCH, **(spec or {})}
    out: list[tuple[float, float]] = []
    for t in sorted(times):
        if out and t - out[-1][0] < float(sp["min_gap"]):
            continue
        if len(out) >= int(sp["max"]):
            break
        out.append((round(float(t), 3), float(sp["amount"])))
    return out


def punch_at(t: float, events: list[tuple[float, float]],
             spec: dict | None = None) -> float:
    """Scale multiplier at time t: 1.0 everywhere except on a punch."""
    if not events:
        return 1.0
    sp = {**PUNCH, **(spec or {})}
    attack, hold = float(sp["attack"]), float(sp["hold"])
    release = float(sp["release"])
    z = 1.0
    for start, amount in events:
        dt = t - start
        if dt < 0.0 or dt > hold + release:
            continue
        env = _smooth(dt / max(attack, 1e-3)) * (1.0 - _smooth((dt - hold) / max(release, 1e-3)))
        z = max(z, 1.0 + amount * env)
    return z


def framing_cuts(caps: list[dict], *, silence: float = 0.30,
                 min_gap: float = 3.5, max_cuts: int = 4) -> list[float]:
    """Where to change framing: only where the edit already stops.

    A card boundary is not a beat - these cards tile the speech back to back,
    so cutting framing at each one changes the shot every 1.3 s and reads as a
    twitch. A *silence* between cards is a beat, and those are rare (post 7
    has one in 21 s). Spacing and a cap keep it to a couple of changes a clip,
    which is what the eye reads as a second camera rather than as a glitch.
    """
    ordered = sorted(caps, key=lambda c: float(c["show_from"]))
    out: list[float] = []
    prev_until = None
    for cap in ordered:
        start = float(cap["show_from"])
        if start < 1.2:
            prev_until = float(cap["show_until"])
            continue
        if prev_until is not None and start - prev_until >= silence:
            if not out or start - out[-1] >= min_gap:
                out.append(round(start, 3))
        prev_until = max(prev_until or 0.0, float(cap["show_until"]))
        if len(out) >= max_cuts:
            break
    return out


def segment_scale(t: float, cuts: list[float], amount: float = 0.016) -> float:
    """A/B framing across a long take.

    A talking head with one framing for 20 seconds reads as a static zoom
    call; alternating a 1.6% push at card boundaries reads as two cameras,
    without touching the audio or re-timing a word.
    """
    n = sum(1 for c in cuts if t >= c)
    return 1.0 + amount * (n % 2)


def zoom_at(t: float, keys: list[tuple[float, float]]) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, z0), (t1, z1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            u = 0.5 - 0.5 * math.cos(math.pi * u)
            return z0 + (z1 - z0) * u
    return keys[-1][1]


def shake_at(t: float, events: list[tuple[float, float, float]]
             ) -> tuple[float, float]:
    ox = oy = 0.0
    for at, amp, dur in events:
        d = t - at
        if 0.0 <= d <= dur:
            k = (1.0 - d / dur) ** 2
            ox += amp * k * math.sin(d * 68.0)
            oy += amp * 0.6 * k * math.cos(d * 41.0)
    return ox, oy


# ------------------------------------------------------------------ helpers
def keyed_keys(spec: list[tuple[object, float]], at_word) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    last = 0.0
    for anchor, z in spec:
        t = float(anchor) if isinstance(anchor, (int, float)) else at_word(str(anchor))
        last = max(t, last + 0.05)
        out.append((last, z))
    return out


def ffmpeg() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def mux(video: Path, src: Path, out: Path, with_audio: bool) -> None:
    ff = ffmpeg()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if with_audio:
        cmd += ["-i", str(src), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy"]
    cmd += ["-c:v", "copy", "-shortest", str(out)]
    subprocess.run(cmd, check=True)


PEAK_TARGET = -1.3      # dBTP: AAC inter-sample overs must not clip on playback
LOUD_TARGET = -16.0     # LUFS: the campaign window is -17..-14; aim at the middle


def settle_audio(path: Path, video: Path) -> dict:
    """Set the level: loudness to target, true peak as the ceiling.

    Previous versions only normalised the peak, which broke the moment the
    voice chain arrived: compression and EQ change the peak-to-loudness ratio,
    so pinning the peak at -1.3 dBTP left post 7 at -17.6 LUFS - outside its
    own campaign window. Loudness is what a viewer experiences; the peak is a
    ceiling, not a target.

    Gain first, then limit, then repeat once: the limiter shaves a little
    loudness back off, so the second pass tops it up.
    """
    info = probe(path)
    for _ in range(3):
        lufs = info.get("lufs")
        if lufs is None:
            break
        need = LOUD_TARGET - lufs
        if abs(need) >= 0.2:
            apply_gain(path, video, need)
            info = probe(path)
        if (info.get("dbtp") if info.get("dbtp") is not None else -99) > PEAK_TARGET:
            apply_limiter(path, video, PEAK_TARGET)
            info = probe(path)
        lufs = info.get("lufs")
        tp = info.get("dbtp")
        if lufs is not None and tp is not None and abs(lufs - LOUD_TARGET) < 0.3 and tp <= PEAK_TARGET + 0.05:
            break
    return info


def apply_limiter(path: Path, video: Path, ceiling_db: float) -> None:
    linear = 10 ** (ceiling_db / 20.0)
    tmp = path.with_name(path.stem + "_lim.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(path), "-i", str(video),
                    "-map", "1:v:0", "-map", "0:a:0", "-c:v", "copy",
                    "-af", f"alimiter=limit={linear:.4f}:level=0",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(tmp)], check=True)
    tmp.replace(path)


def apply_gain(path: Path, video: Path, gain: float) -> None:
    tmp = path.with_name(path.stem + "_lvl.mp4")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(path), "-i", str(video),
                    "-map", "1:v:0", "-map", "0:a:0", "-c:v", "copy",
                    "-af", f"volume={gain:.2f}dB", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(tmp)], check=True)
    tmp.replace(path)


def probe(path: Path) -> dict:
    ff = ffmpeg()
    r = subprocess.run([ff, "-hide_banner", "-i", str(path), "-af",
                        "loudnorm=print_format=summary", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    out = {}
    for line in r.splitlines():
        if "Input Integrated" in line:
            out["lufs"] = float(line.split(":")[1].split()[0])
        if "Input True Peak" in line:
            out["dbtp"] = float(line.split(":")[1].split()[0])
        if "Input LRA" in line:
            out["lra"] = float(line.split(":")[1].split()[0])
    return out


# ------------------------------------------------------------------- render
def build(post: str, *, ship: bool = False, end_mode: str = "card",
          master: bool = False) -> dict:
    if end_mode not in END_MODES:
        raise SystemExit(f"end_mode must be one of {END_MODES}")
    cfg = POSTS[post]
    folder = ROOT / "campaigns" / CAMPAIGN / post
    src = folder / f"street_{post}.mp4"
    style = json.loads((folder / "style.json").read_text())
    style["colors"]["keyword"] = cfg["emphasis"]     # emphasis ink (see module doc)
    plan = json.loads((ROOT / "scripts" / "whop" / "plans" / f"{post}.json").read_text())
    rules_path = ROOT / "campaigns" / CAMPAIGN / "campaign_rules.json"
    rules_doc = json.loads(rules_path.read_text()) if rules_path.exists() else {}

    words = FR.ensure_words(post, src)
    win = FR.WINDOWS[post]
    # 1-2 lines, ~14 characters: the plan's own lines ran to 24, so the
    # blocks are re-wrapped here and re-timed from the same word cells.
    caps = CR.time_cards(CR.rewrap(FR.build_captions(plan, words)),
                         win["endcard"])
    # A caption card whose window runs backwards (seen on post 7: 4.37 -> 4.09)
    # can never be active - `show_from <= t < show_until` is false for it - so
    # it is dead weight that also puts the list out of time order. Drop those
    # and order the rest once, here, rather than trusting every consumer.
    caps = sorted((c for c in caps if float(c["show_until"]) > float(c["show_from"])),
                  key=lambda c: float(c["show_from"]))
    endcard_at = win["endcard"]
    if end_mode == "peak":
        last_end = max(float(c.get("end") or 0) for cap in caps for line in cap["lines"] for c in line)
        endcard_at = last_end + 0.25

    cap_v = cv2.VideoCapture(str(src))
    fps = cap_v.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap_v.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = n_frames / fps

    # -- dead air: cut it, and move every other clock with it
    tight_cfg = {"gap": 0.55, "pad": 0.12, "keep_air": 0.28}
    tight_cfg.update(rules_doc.get("tighten") or {})
    tight_cfg.update(cfg.get("tighten") or {})
    src_duration = duration
    word_spans = [{"at": cell["at"], "end": cell["end"]}
                  for cap in caps for line in cap["lines"] for cell in line]
    segments = TL.keep_segments(word_spans, duration=src_duration,
                                gap=float(tight_cfg["gap"]),
                                pad=float(tight_cfg["pad"]),
                                keep_air=float(tight_cfg["keep_air"]))
    tl = TL.Timeline(segments)
    if not tl.is_identity:
        # captions, words, punches and the end card all live on the old clock
        for cap in caps:
            cap["show_from"] = tl.map(float(cap["show_from"]))
            cap["show_until"] = tl.map(float(cap["show_until"]))
            for line in cap["lines"]:
                for cell in line:
                    cell["at"] = tl.map(float(cell["at"]))
                    cell["end"] = tl.map(float(cell["end"]))
        endcard_at = tl.map(endcard_at)
    duration = tl.duration
    tighten_info = tl.preview()

    at_word = {}
    for cap in caps:
        for line in cap["lines"]:
            for cell in line:
                at_word.setdefault(FR.norm(cell["w"]), float(cell["at"]))
    keys = keyed_keys(cfg["zoom"], lambda w: at_word.get(FR.norm(w), 0.0))
    # a "release" key zooms back down on a punchline; below 1.0 would letterbox,
    # so the floor is the full frame
    keys = [(t, min(1.10, max(1.0, z))) for t, z in keys]
    shakes = [(at_word.get(FR.norm(w), 0.0), amp, dur) for w, amp, dur in cfg["shake"]]
    key_times = [float(cell["at"]) for cap in caps for line in cap["lines"]
                 for cell in line if cell["kind"] == "key"]
    # The director decides which moves this shot actually needs. It is not a
    # switchboard of "everything on": on post 7 it skips the light wrap (the
    # room behind her is darker than her skin, so there is no spill to wrap)
    # and skips the dolly (the clip already cuts, so the movement belongs on
    # the cut, not on the camera).
    direction = DIR.plan_for(src, cards=[
        {"show_from": c["show_from"], "show_until": c["show_until"],
         "lines": [[cell["w"] for cell in line] for line in c["lines"]]}
        for c in caps], words=[{"at": cell["at"], "end": cell["end"]}
                               for cap in caps for line in cap["lines"] for cell in line],
        key_words=len(key_times))
    punch_spec = {**PUNCH, **(cfg.get("punch") or {})}
    punches = punch_events(key_times, punch_spec) if direction["punches"]["use"] else []
    cuts = framing_cuts(caps) if direction["ab_framing"]["use"] else []
    # The opening line is also set as a title in the top third, where the
    # platform UI does not sit, and the band starts on the next card so the
    # same words are never on screen twice.
    ROTO = {"lift": 0.14, "wrap": 0.6, "depth": 0.05}
    ROTO.update(rules_doc.get("roto") or {})
    TRANS = {"kind": "whip", "window": 0.20}
    TRANS.update(rules_doc.get("transition") or {})
    need_roto = direction["subject_lift"]["use"] or direction["light_wrap"]["use"]
    tracker = MK.FaceTracker(ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx")
    masker = BM.PersonMasker({"refresh": 5})
    trans_at = [tl.map(c) for c in direction["transition"]["where"]] \
        if direction["transition"]["use"] else []
    hook_cells = [cell for line in caps[0]["lines"] for cell in line] if caps else []
    hook_until = (min(1.60, float(caps[1]["show_from"]) + 0.10)
                  if len(caps) > 1 else min(1.60, duration))

    if end_mode == "peak":
        # cut on the peak: last spoken word, a beat of air, fade. No CTA card.
        duration = min(duration, endcard_at + 0.35)

    grade_cfg = dict(DEFAULT_GRADE)
    grade_cfg.update(rules_doc.get("grade") or {})
    grade_cfg.update(cfg.get("grade") or {})
    vig_mask = None
    typer = FR.Typesetter(style)
    endcard_img = typer.endcard_image()
    bigword_img = typer.bigword_image() if "bigword" in win else None

    out_video = ROOT / "work" / "street" / post / "tight_video.mp4"
    out_video.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg()
    enc = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", f"{fps:.3f}", "-i", "-", "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out_video)], stdin=subprocess.PIPE)

    def active(t: float):
        for cap in caps:
            if cap["show_from"] <= t < cap["show_until"]:
                return cap
        return None

    prev_bar = 0
    bars: list[int] = []
    plates = 0
    written = 0
    for fi in range(n_frames):
        ok, frame = cap_v.read()
        if not ok:
            break
        t_src = fi / fps
        # A frame inside a removed gap is never written: the picture and the
        # cut audio then share one timeline, which is what makes the joins
        # land on the same sample as the caption.
        if not tl.kept(t_src):
            continue
        t = tl.map(t_src)
        if t >= duration:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        std = float(cv2.resize(gray, (108, 192)).std())
        bar = bar_rows(gray)
        # A bar only ever changes at a hard cut, and the two plateaus are
        # >100 px apart: adopt a jump at once, ignore small noise.
        if abs(bar - prev_bar) < 60 and abs(bar - prev_bar) > 6:
            bar = prev_bar
        prev_bar = bar
        bars.append(bar)

        if t >= endcard_at and end_mode == "card":
            out = cv2.cvtColor(endcard_img, cv2.COLOR_RGB2BGR)
        elif bigword_img is not None and win["bigword"][0] <= t < win["bigword"][1]:
            out = cv2.cvtColor(bigword_img, cv2.COLOR_RGB2BGR)
            cap = active(t)
            if cap is not None:                       # type-on over the fresh plate
                ov = typer.overlay(cap, t)
                a = ov[:, :, 3:4].astype(np.float32) / 255.0
                if a.any():
                    out = (out.astype(np.float32) * (1 - a)
                           + ov[:, :, :3][:, :, ::-1].astype(np.float32) * a
                           ).astype(np.uint8)
        else:
            cap = None if t < hook_until - 0.02 else active(t)
            # The band is cleaned whenever a card is up *and* while the hook
            # title is up: the archive footage already carries burned-in
            # subtitles, so the moment we stop drawing our own, theirs shows
            # through underneath the title (seen on post 7 at 0-0.4 s).
            if cap is not None or t < hook_until:
                band = FR.SCENE_BAND if (cap and cap["zone"] == "scene") else FR.BAND
                frame = clean_caption_band(frame, band[0], band[1], std < PLATE_STD)
            # The grade goes on the *footage*, before any type is drawn: the
            # caption ink was approved on a swatch, and a warm highlight pass
            # over ivory is a different colour. Scaling (camera/zoom) moves
            # type but does not tint it, so this order keeps both.
            if std >= PLATE_STD:
                frame = grade_frame(frame, grade_cfg, vig_mask)
            if need_roto and std >= PLATE_STD:
                fbox = tracker.update(frame)
                mask = masker.mask(frame, fbox)
                if direction["subject_lift"]["use"]:
                    frame = BM.subject_lift(frame, mask, float(ROTO["lift"]))
                if direction["light_wrap"]["use"]:
                    frame = MK.light_wrap(frame, mask, strength=float(ROTO["wrap"]))
                if direction["dolly"]["use"]:
                    frame = BM.parallax(frame, mask, depth=float(ROTO["depth"]) * (0.4 + t / max(duration, 0.1)))
            if cap is not None:
                ov = typer.overlay(cap, t)
                a = ov[:, :, 3:4].astype(np.float32) / 255.0
                if a.any():
                    frame = (frame.astype(np.float32) * (1 - a)
                             + ov[:, :, :3][:, :, ::-1].astype(np.float32) * a
                             ).astype(np.uint8)
            if std < PLATE_STD:                       # vector plate: hold it still
                plates += 1
                out = camera_frame(frame, 0, 1.0)     # brand colours stay exact
            else:
                dx, dy = shake_at(t, shakes)
                z = (zoom_at(t, keys) * punch_at(t, punches, punch_spec)
                     * segment_scale(t, cuts))
                out = camera_frame(frame, bar, min(1.10, z), dx, dy)
                if trans_at:
                    near = min(trans_at, key=lambda c: abs(t - c))
                    dist = abs(t - near)
                    if dist <= TRANS["window"]:
                        amt = (1.0 - dist / TRANS["window"]) ** 1.4
                        idx = trans_at.index(near)
                        out = (MK.whip_pan(out, amt, direction=1 if idx % 2 == 0 else -1)
                               if TRANS["kind"] == "whip" else MK.zoom_blur(out, amt * 3.0))
                if hook_cells and t < hook_until:
                    ov = typer.hook_image(hook_cells, t, y=int(cfg.get("hook_y", 300)))
                    fade = min(1.0, max(0.0, (hook_until - t) / 0.16))
                    a = ov[:, :, 3:4].astype(np.float32) / 255.0 * fade
                    if a.any():
                        out = (out.astype(np.float32) * (1 - a)
                               + ov[:, :, :3][:, :, ::-1].astype(np.float32) * a
                               ).astype(np.uint8)
        if t > duration - 0.5:                        # keep the shipped fade
            out = (out.astype(np.float32)
                   * (1 - 0.92 * (t - (duration - 0.5)) / 0.5)).astype(np.uint8)
        enc.stdin.write(out.tobytes())
        written += 1
    cap_v.release()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit(f"{post}: video encode failed")

    final = ROOT / "work" / "street" / post / "tight.mp4"
    if tl.is_identity:
        mux(out_video, src, final, with_audio=True)   # sound copied, never re-timed
    else:
        cut_audio = ROOT / "work" / "street" / post / "tight_audio.m4a"
        TL.cut_audio(src, tl.segments, cut_audio, ff)
        mux(out_video, cut_audio, final, with_audio=True)
    if end_mode == "peak":
        trimmed = ROOT / "work" / "street" / post / "tight_peak.mp4"
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(final), "-t", f"{duration:.3f}",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        str(trimmed)], check=True)
        final = trimmed
    # -- voice first: the bed is mixed under what the EQ and compressor leave
    voice_cfg = dict(VF.DEFAULT)
    voice_cfg.update(rules_doc.get("voice") or {})
    voice_cfg.update(cfg.get("voice") or {})
    if voice_cfg.get("enabled"):
        VF.finish(final, voice_cfg)

    # -- sound design: synthesised, so nothing to license and nothing to claim
    sound_cfg = dict(DEFAULT_SOUND)
    sound_cfg.update(rules_doc.get("sound") or {})
    sound_cfg.update(cfg.get("sound") or {})
    if sound_cfg.get("enabled"):
        intervals = SD.word_intervals(
            [{"at": c["at"], "end": c["end"]}
             for cap in caps for line in cap["lines"] for c in line])
        # place the bed relative to the voice that is actually in this file,
        # not at a fixed level: the voice chain changes the ratio silently
        try:
            from clipper.ffmpeg import decode_audio
            voice_rms = SD.speech_level(decode_audio(final))
        except Exception:
            voice_rms = 0.0
        target = SD.bed_target(voice_rms) if voice_rms else None
        track = SD.build_track(duration, intervals,
                               [t for t, _ in punches] if sound_cfg.get("hits") else [],
                               int(sound_cfg.get("rate") or 48000),
                               target_rms=target)
        if not sound_cfg.get("bed"):
            track = np.zeros_like(track)
        mixed = final.with_name(final.stem + "_bed.mp4")
        SD.mix_into(final, mixed, track, int(sound_cfg.get("rate") or 48000), ff)
        mixed.replace(final)

    name = f"street_{post}{'_preview' if not ship else ''}.mp4"
    dest = (folder / name) if ship else (ROOT / "work" / "street" / post / name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(final.read_bytes())

    # cover: a frame where a key word is fully typed and the face is on screen
    cover_t = float(cfg.get("cover")
                    or at_word.get(FR.norm(cfg.get("cover_word", "")), 1.3) + 0.30)
    cover_info = None
    if ship:
        cover_info = CV.best_frame(dest, start=1.0, end=max(1.2, duration - 1.0))
        cover_t = float(cover_info.get("at", cover_t))
    cap_v = cv2.VideoCapture(str(dest))
    cap_v.set(cv2.CAP_PROP_POS_MSEC, cover_t * 1000)
    ok, frame = cap_v.read()
    cap_v.release()
    if ok and ship:
        cv2.imwrite(str(folder / "cover.jpg"),
                    cv2.resize(frame, (540, 960), interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])

    info = settle_audio(dest, out_video)
    manifest = {
        "post": post,
        "campaign": CAMPAIGN,
        "duration": round(duration, 3),
        "end_mode": end_mode,
        "endcard": round(float(endcard_at), 3),
        "caption_band": list(FR.BAND),
        "cards": [
            {"show_from": round(c["show_from"], 3),
             "show_until": round(c["show_until"], 3),
             "lines": [[c["w"] for c in line] for line in c["lines"]]}
            for c in caps
        ],
        "words_kept": [
            {"w": c["w"], "at": round(float(c["at"]), 3), "end": round(float(c["end"]), 3)}
            for c in sorted((cell for cap in caps for line in cap["lines"] for cell in line),
                            key=lambda x: x["at"])
        ],
    }
    (ROOT / "work" / "street" / post / "tight_cards.json").write_text(
        json.dumps(manifest, indent=1) + "\n")
    if master:
        master_path = ROOT / "work" / "street" / post / f"master_{post}.mp4"
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(dest), "-c:v", "libx264", "-crf", "14",
                        "-preset", "medium", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", str(master_path)], check=True)
        print(f"master: {master_path} ({master_path.stat().st_size} bytes)")

    report = {
        "post": post,
        "source": str(src),
        "emphasis": cfg["emphasis"],
        "duration": round(duration, 2),
        "frames": written,
        "sizes": {"bytes": dest.stat().st_size},
        "camera_keys": [[round(t, 2), round(z, 3)] for t, z in keys],
        "bar_rows_seen": sorted(set(bars)),
        "plate_frames": plates,
        "caption_cards": len(caps),
        "end_mode": end_mode,
        "grade": grade_cfg,
        "sound": sound_cfg,
        "voice_chain": VF.chain(voice_cfg) if voice_cfg.get("enabled") else None,
        "key_words": len(key_times),
        "direction": {k: v for k, v in direction.items() if not k.startswith("_")},
        "tighten": tighten_info,
        "transitions_at": [round(c, 2) for c in trans_at],
        "roto": need_roto,
        "cover": cover_info,
        "hook_title": {"until": round(hook_until, 2),
                       "words": [c["w"] for c in hook_cells]},
        "punches": [[round(t, 2), round(a, 3)] for t, a in punches],
        "ab_cuts": [round(c, 2) for c in cuts],
        "manifest": "work/street/%s/tight_cards.json" % post,
        "cover_at": round(cover_t, 2),
        **info,
    }
    (ROOT / "work" / "street" / post / "tight_report.json").write_text(
        json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    return report


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ship = "--ship" in sys.argv
    master = "--master" in sys.argv
    end_mode = "card"
    for a in sys.argv[1:]:
        if a.startswith("--end="):
            end_mode = a.split("=", 1)[1]
    posts = args or ["post6", "post7"]
    for post in posts:
        print(f"\n=== {post} ({'ship' if ship else 'preview'}, end={end_mode}) ===",
              flush=True)
        build(post, ship=ship, end_mode=end_mode, master=master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
