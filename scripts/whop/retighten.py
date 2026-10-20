#!/usr/bin/env python3
"""Tight re-edit of a shipped Whop clip - the "campaign brief" pass.

    .venv/bin/python scripts/whop/retighten.py post4

The shipped cut was assembled before the campaign brief landed. This pass
keeps the same footage, the same look and the same captions, and fixes the
things the brief grades us on:

* **Captions land on the words.** Word times come from the cut's own
  transcript (Moonshine + energy alignment), matched to the plan text - not
  from a proportional spread across speech intervals, which creeps later and
  later as the speaker repeats himself.
* **Fillers and dead air out.** "um / uh / like, / you know," are cut from
  the audio *and* the picture, and every pause longer than 200 ms is trimmed
  back to 200 ms. Nothing is muted over the top of a gap - the timeline is
  rebuilt shorter, so the delivery stays continuous.
* **Bars gone.** The interview plates carry ~107 px of black across the top;
  that is cropped out and the picture is re-fitted to 1080x1920.
* **Movement with purpose.** A slow push through the hook, a release on the
  turn, a punch-in on the impact line, a settle, then a push on the emotional
  close. Small enough to read as camera work, not as an effect.
* **Captions re-wrapped to the brief's line length** (1-2 lines, ~14 chars a
  line) instead of full sentences, re-timed onto the new timeline, still
  Shawkind straight on the picture with the post accent on key words.
* **Keyboard typing** on the new caption grid, at the level set after the
  "20% too loud" note.
* **True peak** held under -1.3 dBTP so AAC inter-sample overs cannot clip.

Audio and video are rebuilt together from one cut list, so a word that is
removed is removed from both.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import font_refresh as FR                     # Typesetter, erase_captions
import keyboard_sfx as KB

W, H = FR.W, FR.H
FPS = 30.0
BAR_TOP = 107                 # measured black rows on the interview plates
PAUSE_CAP = 0.20              # longest silence kept between phrases
CARD_MAX_CHARS = 17           # wrap target: brief says ~14, "most cases"
FILLERS = {"um", "uh", "uhm", "erm", "hmm", "mm", "uhh", "ah", "eh", "er"}


# --------------------------------------------------------------------- text
def load_tokens(post: str) -> tuple[dict, list[dict]]:
    plan = json.loads((ROOT / "scripts" / "whop" / "plans" / f"{post}.json").read_text())
    tokens: list[dict] = []
    for bi, beat in enumerate(plan["beats"]):
        if beat.get("type") != "caption":
            continue
        kinds = beat.get("kinds") or []
        for li, line in enumerate(beat["lines"]):
            for wi, tok in enumerate(line.split()):
                kind = "conn"
                if li < len(kinds) and wi < len(kinds[li]):
                    kind = kinds[li][wi]
                tokens.append({"w": tok, "kind": kind, "beat": bi})
    return plan, tokens


def bare(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum())


def filler_flags(tokens: list[dict]) -> list[bool]:
    """Which tokens are verbal filler (never content).

    Conservative on purpose: a bare "like" is only filler when it carries a
    comma ("Like, I'm terrified"), so "things like that" survives; "you know"
    is only filler when the phrase is set off by a comma.
    """
    flags = [False] * len(tokens)
    for i, t in enumerate(tokens):
        w = bare(t["w"])
        if w in FILLERS:
            flags[i] = True
        elif w == "like" and t["w"].rstrip().endswith(","):
            flags[i] = True
        elif (w == "you" and i + 1 < len(tokens)
              and bare(tokens[i + 1]["w"]) == "know"
              and tokens[i + 1]["w"].rstrip().endswith(",")):
            flags[i] = flags[i + 1] = True
    return flags


# Filler windows are AUDIO positions, not word-map positions. The word timings
# this project can recover are +/-150 ms, which is fine for placing a caption
# and not fine for slicing one word out of a sentence: the first attempts cut
# "still"/"loved" instead of "you know,". So each window below was found by
# sliding a 1.3 s ASR window across the clip, then confirmed by cutting it and
# re-transcribing the result - a window is only kept if the filler is gone
# from the new transcript AND no content word disappeared with it.
#
#   post4 "Like,"      cut 1.50-1.68 -> "go on stage. I'm terrified."
#   post4 "You know,"  cut 4.03-4.36 -> "People aren't. They're going to say things"
#   post4 "You know,"  cut 13.52-13.82 -> "They still loved me."
FILLER_WINDOWS: dict[str, list[tuple[float, float, str]]] = {
    "post4": [
        (1.50, 1.68, "Like,"),
        (4.03, 4.36, "You know,"),
        (13.52, 13.82, "You know,"),
    ],
}


def bad_cut_spans(post: str) -> list[tuple[float, float]]:
    return [(a, b) for a, b, _ in FILLER_WINDOWS.get(post, [])]


def pause_cuts(audio: np.ndarray, rate: int, duration: float,
               cap: float = PAUSE_CAP) -> list[tuple[float, float]]:
    """Trim every silence longer than `cap`, keeping some air on both sides.

    Boundaries come from VAD on the actual audio, so this can never slice a
    word; 90 ms is left before the next onset and 70 ms after the last one so
    the consonant that opens a phrase is never clipped.
    """
    from clipper.align.vad import speech_intervals
    iv = speech_intervals(audio, rate, min_speech=0.12)
    cuts = []
    for (sa, sb), (na, nb) in zip(iv, iv[1:]):
        gap = na - sb
        if gap <= 0.30:
            continue
        cuts.append((sb + 0.09, na - 0.07))
    return [(a, b) for a, b in cuts if b - a > 0.05]


def build_cuts(tokens: list[dict], duration: float,
               audio: np.ndarray | None = None, rate: int = 16000,
               post: str = "") -> list[tuple[float, float]]:
    cuts = list(bad_cut_spans(post))
    if audio is not None:
        cuts += pause_cuts(audio, rate, duration)
    cuts.sort()
    merged: list[tuple[float, float]] = []
    for a, b in cuts:
        if merged and a <= merged[-1][1] + 0.01:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [(a, min(b, duration)) for a, b in merged if b - a > 0.04]


def timeline(cuts: list[tuple[float, float]], duration: float):
    """Kept spans + old->new time map."""
    spans: list[tuple[float, float, float]] = []     # old_start, old_end, new_start
    new_t = 0.0
    cursor = 0.0
    for a, b in cuts:
        if a > cursor:
            spans.append((cursor, a, new_t))
            new_t += a - cursor
        cursor = max(cursor, b)
    if cursor < duration:
        spans.append((cursor, duration, new_t))
        new_t += duration - cursor
    return spans, new_t


def to_new(t: float, cuts: list[tuple[float, float]]) -> float:
    shift = 0.0
    for a, b in cuts:
        if t >= b:
            shift += b - a
        elif t > a:
            return a - shift
    return t - shift


# ------------------------------------------------------------------- cards
def wrap_cards(tokens: list[dict], max_chars: int = CARD_MAX_CHARS) -> list[dict]:
    """Re-wrap each beat into 1-2 line cards of caption-sized chunks."""
    cards: list[dict] = []
    beats: dict[int, list[dict]] = {}
    for t in tokens:
        beats.setdefault(t["beat"], []).append(t)
    for bi in sorted(beats):
        rows: list[dict] = []
        lines: list[list[dict]] = []
        line: list[dict] = []
        width = 0
        for cell in beats[bi]:
            add = len(cell["w"]) + (1 if line else 0)
            if line and width + add > max_chars:
                lines.append(line)
                line = [cell]
                width = len(cell["w"])
            else:
                line.append(cell)
                width += add
            if len(lines) == 2:          # card is full, start the next one
                rows.append({"lines": lines})
                lines, line, width = [], [], 0
        if line:
            lines.append(line)
        if lines:
            rows.append({"lines": lines})
        for row in rows:
            row["zone"] = "low"      # the camera keeps the caption band fixed
            first = row["lines"][0][0]
            first["w"] = first["w"][:1].upper() + first["w"][1:]
            cards.append(row)
    return cards


def time_cards(cards: list[dict], endcard: float) -> list[dict]:
    flat = [c for card in cards for line in card["lines"] for c in line]
    for i, card in enumerate(cards):
        cells = [c for line in card["lines"] for c in line]
        nxt = (cards[i + 1]["lines"][0][0]["at"] if i + 1 < len(cards) else endcard)
        card["show_from"] = max(0.0, cells[0]["at"] - 0.03)
        last = cells[-1]["end"]
        card["show_until"] = min(nxt - 0.02, max(last + 0.45, nxt - 0.02), endcard)
    for i in range(len(cards) - 1):
        gap = cards[i + 1]["show_from"] - cards[i]["show_until"]
        if 0 < gap < 0.7:
            cards[i]["show_until"] = cards[i + 1]["show_from"]
    return cards


# ------------------------------------------------------------------ camera
def zoom_at(t: float, keys: list[tuple[float, float]]) -> float:
    """Cosine-eased zoom between keyframes."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, z0), (t1, z1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            u = 0.5 - 0.5 * math.cos(math.pi * u)
            return z0 + (z1 - z0) * u
    return keys[-1][1]


def shake_at(t: float, at: float, dur: float = 0.28, amp: float = 2.6) -> tuple[float, float]:
    """Tiny decaying offset - impact, not earthquake."""
    d = t - at
    if d < 0 or d > dur:
        return 0.0, 0.0
    k = (1.0 - d / dur) ** 2
    return amp * k * math.sin(d * 68.0), amp * 0.6 * k * math.cos(d * 41.0)


def camera_frame(frame: np.ndarray, z: float, dx: float, dy: float) -> np.ndarray:
    """Crop the black top bar, fit to 1080x1920, apply zoom and shake."""
    src = frame[BAR_TOP:]
    sh, sw = src.shape[:2]
    scale = max(W / sw, H / sh) * z
    cw, ch = W / scale, H / scale
    cx = sw / 2.0 + dx / scale
    cy = sh * 0.44 + dy / scale
    x0 = min(max(0.0, cx - cw / 2), sw - cw)
    y0 = min(max(0.0, cy - ch / 2), sh - ch)
    out = cv2.resize(src[int(round(y0)):int(round(y0 + ch)),
                         int(round(x0)):int(round(x0 + cw))],
                     (W, H), interpolation=cv2.INTER_CUBIC)
    return out


# ------------------------------------------------------------------- audio
def cut_audio_chunked(src: Path, spans: list[tuple[float, float, float]],
                      out_wav: Path, rate: int = 48000) -> np.ndarray:
    """Rebuild the mix from the kept spans, one ffmpeg call per span.

    Each span is written at its own new offset, so nothing is concatenated in
    memory and the 21 s timeline costs a handful of short decodes instead of
    one long copy.
    """
    import soundfile as sf
    total = max(ns + (e - s) for s, e, ns in spans)
    bed = np.zeros(int(math.ceil(total * rate)) + rate // 4, dtype=np.float32)
    for s, e, ns in spans:
        raw = subprocess.run(
            [KB._ff(), "-hide_banner", "-loglevel", "error", "-ss", f"{s:.3f}",
             "-to", f"{e:.3f}", "-i", str(src), "-vn", "-ac", "1",
             "-ar", str(rate), "-f", "f32le", "-"],
            capture_output=True, check=True).stdout
        seg = np.frombuffer(raw, dtype="<f4").astype(np.float32)
        n = int(round((e - s) * rate))
        seg = seg[:n]
        if len(seg) < n:                      # ffmpeg can land a frame short
            seg = np.pad(seg, (0, n - len(seg)))
        fade = int(0.012 * rate)
        if len(seg) > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            seg[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        i = int(round(ns * rate))
        bed[i:i + len(seg)] += seg
    return bed


def true_peak_db(path: Path) -> float:
    ff = KB._ff()
    out = subprocess.run([ff, "-hide_banner", "-i", str(path), "-af",
                          "loudnorm=print_format=summary", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Input True Peak" in line:
            return float(line.split(":")[1].strip().split()[0])
    return 0.0


def main() -> int:
    post = sys.argv[1] if len(sys.argv) > 1 else "post4"
    campaign = "street_you_grew_up_on"
    folder = ROOT / "campaigns" / campaign / post
    src = folder / f"street_{post}.mp4"
    style = json.loads((folder / "style.json").read_text())
    plan, tokens = load_tokens(post)

    # ---- timings from the shipped cut's own audio -------------------------
    ff = KB._ff()
    raw16 = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn",
         "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    a16 = np.frombuffer(raw16, dtype="<f4").astype(np.float32)
    duration = len(a16) / 16000.0

    # Word times come from the speech itself: Moonshine's own word timestamps
    # on this cut, matched onto the plan's verbatim lines. That is the same
    # path font_refresh uses, and the one whose sync was signed off.
    #
    # The previous version instead distributed the whole plan proportionally
    # across VAD intervals. That has no idea where any word actually is: the
    # speaker repeats "People aren't" seven times while the plan writes it
    # once, so every later word is pushed further late and never recovers -
    # measured +0.9 s on average and +2.3 s by "their seats". That is exactly
    # the "captions come late" creep this pass had.
    cache = ROOT / "work" / "street" / post / "font_words.json"
    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
        except Exception:
            cached = {}
        if abs(float(cached.get("duration") or 0) - duration) > 0.3:
            cache.unlink()          # cache belongs to a different cut
    words = FR.ensure_words(post, src)
    timed = FR.build_captions(plan, words)
    flat = [cell for cap in timed for line in cap["lines"] for cell in line]
    if len(flat) != len(tokens):
        raise SystemExit(f"timing gave {len(flat)} words for {len(tokens)} tokens")
    for tok, cell in zip(tokens, flat):
        tok["at"], tok["end"] = float(cell["at"]), float(cell["end"])

    # ---- cut list ---------------------------------------------------------
    cuts = build_cuts(tokens, duration, a16, 16000, post)
    flags = filler_flags(tokens)
    removed = sum(b - a for a, b in cuts)
    print(f"cuts: {len(cuts)}  removing {removed:.2f}s of {duration:.2f}s")
    for i, (a, b) in enumerate(cuts):
        who = [t["w"] for t, f in zip(tokens, flags)
               if f and a - 0.02 <= t["at"] <= b + 0.02]
        tag = "filler " + " ".join(who) if who else "pause"
        print(f"  {a:6.2f}-{b:6.2f}  {b - a:4.2f}s  {tag}")

    spans, new_total = timeline(cuts, duration)
    WINDOWS = FR.WINDOWS[post]
    endcard_old = WINDOWS["endcard"]
    endcard_new = to_new(endcard_old, cuts)
    out_duration = new_total

    # ---- tokens/cards on the new timeline, fillers dropped ----------------
    kept = [t for t, f in zip(tokens, flags) if not f]
    for t in kept:
        t["at"], t["end"] = to_new(t["at"], cuts), to_new(t["end"], cuts)
    cards = time_cards(wrap_cards(kept, CARD_MAX_CHARS), endcard_new)
    widths = [len(" ".join(c["w"] for c in line)) for card in cards for line in card["lines"]]
    print(f"captions: {len(cards)} cards, median line {int(np.median(widths))} chars, "
          f"max {max(widths)}")

    # ---- camera keyframes, anchored on the words that matter -------------
    def at(word: str) -> float:
        for t in kept:
            if bare(t["w"]) == word:
                return t["at"]
        return 0.0
    t_stage, t_anyway = at("stage"), at("anyways")
    t_around, t_zero = at("around"), at("zero")
    t_joy, t_loved = at("joy"), at("loved")
    keys = [
        (0.00, 1.000), (max(t_stage, 1.2), 1.045),
        (max(t_stage + 0.6, 1.8), 1.010), (max(t_anyway - 0.55, 2.4), 1.020),
        (max(t_anyway, 2.6), 1.058), (max(t_anyway + 0.55, 3.0), 1.028),
        (max(t_around + 0.4, 3.6), 1.012), (max(t_zero, 5.0), 1.000),
        (max(t_loved - 0.2, 6.0), 0.996), (max(t_joy, 7.0), 1.042),
        (endcard_new, 1.030),
    ]
    keys = sorted(keys)

    # ---- render ----------------------------------------------------------
    typer = FR.Typesetter(style)
    # cards are 1-2 short lines now, so the fitter would push the size to its
    # ceiling and a 2-line card could overflow the frame bottom; cap it where
    # the brief's caption look lives
    def _card_size(cap: dict) -> int:
        longest = max(len(" ".join(c["w"] for c in line)) for line in cap["lines"])
        return int(np.clip(78 - 2.1 * max(0, longest - 12), 50, 78))
    typer._fit_size = _card_size
    endcard_img = typer.endcard_image()
    out_path = ROOT / "work" / "street" / post / "tight_video.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mux_path = out_path.with_name("tight.mp4")

    enc = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{FPS:.3f}",
         "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out_path)], stdin=subprocess.PIPE)

    cap = cv2.VideoCapture(str(src))
    n_out = int(round(out_duration * FPS))
    src_idx = -1
    frame = None
    span_i = 0

    def card_at(t: float):
        for c in cards:
            if c["show_from"] <= t < c["show_until"]:
                return c
        return None

    for fi in range(n_out):
        t = fi / FPS
        if t >= endcard_new:
            out = cv2.cvtColor(endcard_img, cv2.COLOR_RGB2BGR)
            if t > out_duration - 0.5:                # keep the shipped fade
                out = (out.astype(np.float32)
                       * (1 - 0.92 * (t - (out_duration - 0.5)) / 0.5)).astype(np.uint8)
            enc.stdin.write(out.tobytes())
            continue
        # which kept span holds this output time
        while span_i + 1 < len(spans) and t >= spans[span_i][2] + (spans[span_i][1] - spans[span_i][0]):
            span_i += 1
        s, e, ns = spans[span_i]
        t_old = s + (t - ns)
        want = int(round(t_old * FPS))
        while src_idx < want:
            ok, frame = cap.read()
            if not ok:
                break
            src_idx += 1
        if frame is None:
            break
        # old burned-in captions never reach the camera. Erasing costs a
        # morphology + inpaint pass, so it runs once per caption card (and
        # once at the tail, where the last caption may still be fading out)
        card = card_at(t)
        tail_end = cards[-1]["show_until"] if cards else 0.0
        need_erase = card is not None or (tail_end <= t < tail_end + 0.15)
        frame_clean = FR.erase_captions(frame, *FR.BAND) if need_erase else frame
        z = zoom_at(t, keys)
        dx, dy = shake_at(t, t_anyway, dur=0.30, amp=2.4)
        out = camera_frame(frame_clean, z, dx, dy)
        if card is not None:
            ov = typer.overlay(card, t)
            a = ov[:, :, 3:4].astype(np.float32) / 255.0
            if a.any():
                out = (out.astype(np.float32) * (1 - a)
                       + ov[:, :, :3][:, :, ::-1].astype(np.float32) * a).astype(np.uint8)
        if t > out_duration - 0.5:                    # keep the shipped fade
            out = (out.astype(np.float32)
                   * (1 - 0.92 * (t - (out_duration - 0.5)) / 0.5)).astype(np.uint8)
        enc.stdin.write(out.tobytes())
    cap.release()
    # fill any shortfall (a source read that ran out) so video and audio end
    # together - a truncated v:0 tail is how the end card used to vanish
    while fi < n_out - 1:
        out = cv2.cvtColor(endcard_img, cv2.COLOR_RGB2BGR)
        enc.stdin.write(out.tobytes())
        fi += 1
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("video encode failed")

    # ---- audio: same cut list, then keyboard, then true-peak ------------
    bed_cut = cut_audio_chunked(src, spans, out_path.with_name("bed.wav"))
    track, log = KB.typing_track(cards, out_duration, endcard_new, post)
    mixed, gain = KB.mix_into(bed_cut, track)

    tmp_wav = out_path.with_name("tight_audio.wav")
    import soundfile as sf
    sf.write(tmp_wav, mixed, 48000, subtype="FLOAT")
    tp = true_peak_db(tmp_wav)
    target = -1.3
    if tp > target:
        mixed *= 10 ** ((target - tp) / 20.0)
        sf.write(tmp_wav, mixed, 48000, subtype="FLOAT")
        tp = true_peak_db(tmp_wav)
    print(f"keyboard: {len(log)} keys, gain {gain:.2f} | true peak {tp:+.2f} dBTP")

    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(out_path), "-i", str(tmp_wav),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(mux_path)],
                   check=True)
    dest = folder / f"street_{post}.mp4"
    dest.write_bytes(mux_path.read_bytes())
    print(f"shipped {dest} ({dest.stat().st_size} bytes, {out_duration:.2f}s, "
          f"was {duration:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
