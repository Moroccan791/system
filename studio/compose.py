"""Compose the edit — frames, grade, type, flashes, sound.

Frame pipeline per cut:
    decode source segment -> scale/crop 1920x1080 -> per-act grade
      -> type card composite -> optional flash -> pipe to x264

Everything is deterministic from the plan json, so a render can be reproduced
and a single frame can be re-rendered for inspection without redoing the edit.

Sound is the track, shaped by act, written as one pass so the mux cannot drift
against picture.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .grid import Grid, load_audio, SR
from .plan import Plan, Cut
from .ramp import make as make_ramp, mean_speed_of
from .sound import cues_for, render_cues, write_wav
from .track import smooth, track_box
from .typecards import Card, composite, composite_matte, render_card, scrim

OUT_W, OUT_H, OUT_FPS = 1920, 1080, 30

# how loud the track sits in each act, before the final normalise
ACT_GAIN = {"build": 0.62, "drop": 1.0, "out": 0.78}


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


# --------------------------------------------------------------------------
# grade
# --------------------------------------------------------------------------
def grade(frame: np.ndarray, g: dict) -> np.ndarray:
    """Contrast, saturation, gamma, brightness and a shadow tint, in that order.

    Done in float32 on the whole frame: 1080p is 6 MB per buffer, so a handful of
    vectorised ops costs a few milliseconds and keeps the look consistent between
    the test render and the final.
    """
    f = frame.astype(np.float32)
    f = (f - 128.0) * g.get("contrast", 1.0) + 128.0
    # brightness is an OFFSET in 0-255 space. It was written as a multiplier,
    # so a grade of -0.02 multiplied every pixel by -4.1 and turned a shot with
    # a mean luma of 65 into one with a mean of 4.
    f = f + g.get("brightness", 0.0) * 255.0
    if g.get("gamma", 1.0) != 1.0:
        f = 255.0 * np.clip(f / 255.0, 0, 1) ** g["gamma"]
    sat = g.get("saturation", 1.0)
    if sat != 1.0:
        luma = (f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722)[..., None]
        f = luma + (f - luma) * sat
    tint = g.get("shadow_tint")
    if tint:
        # tint only the shadows, so highlights stay clean
        w = np.clip(1.0 - (f.mean(axis=2, keepdims=True) / 160.0), 0.0, 1.0)
        f = f * (1.0 + (np.array(tint, dtype=np.float32) - 1.0) * w * 0.9)
    return np.clip(f, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# decode
# --------------------------------------------------------------------------
_ASPECT_CACHE: dict[str, float] = {}


def _source_aspect(src: str) -> float:
    if src not in _ASPECT_CACHE:
        from .shots import probe

        m = probe(src)
        _ASPECT_CACHE[src] = (m["width"] / m["height"]) if m["height"] else 16 / 9
    return _ASPECT_CACHE[src]


def decode_segment(src: str, t_in: float, dur: float, speed: float) -> list[np.ndarray]:
    """Frames for one cut, already at output size and speed.

    Two layouts, chosen by how far the source is from 16:9:

    COVER  the source is already close to the frame. Scale to fill and crop the
           overflow — what an editor does with a normal shot.
    FIT    the source is a vertical insert or a 4:3 archive clip. Covering it
           would crop to a nostril, so the shot is placed in the middle and the
           space behind it is filled with an enlarged, blurred copy of itself.
           This is the standard broadcast answer and it reads as deliberate;
           black bars read as a mistake.
    """
    aspect = _source_aspect(src)
    # WIDER than the frame (cinema 2.4:1, 2:1) is cropped to fill — that is what
    # an editor does with film footage. NARROWER (vertical inserts, 4:3 archive)
    # is fitted over a blurred fill, because cropping those eats the subject.
    cover = aspect >= 1.55

    timing = ""
    if abs(speed - 1.0) > 1e-3:
        timing = f",setpts={speed:.4f}*PTS"

    if cover:
        vf = (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:"
              f"flags=lanczos,crop={OUT_W}:{OUT_H},setsar=1")
        graph = ["-vf", vf + timing]
    else:
        fc = (
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:"
            f"flags=lanczos,crop={OUT_W}:{OUT_H},boxblur=32:2,"
            f"eq=brightness=-0.12:saturation=0.7[bg];"
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:"
            f"flags=lanczos,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1{timing}[v]"
        )
        graph = ["-filter_complex", fc, "-map", "[v]"]

    cmd = [ffmpeg(), "-nostdin", "-v", "error",
           "-ss", f"{max(0.0, t_in):.4f}", "-i", src,
           "-t", f"{max(0.04, dur):.4f}"] + graph + [
           "-r", str(OUT_FPS), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=False).stdout
    fb = OUT_W * OUT_H * 3
    n = len(raw) // fb
    return [np.frombuffer(raw[i * fb:(i + 1) * fb], dtype=np.uint8)
            .reshape(OUT_H, OUT_W, 3).copy() for i in range(n)]


def decode_ramped(src: str, t_in: float, out_dur: float, ramp) -> list[np.ndarray]:
    """Frames for a speed-ramped cut.

    The ramp lives in output time, so this decodes the whole source span once at
    OUTPUT fps and then samples it along the ramp's time warp, blending the two
    nearest decoded frames. That keeps it to one ffmpeg call per cut and gives
    sub-frame accuracy, instead of one call per frame.
    """
    span = out_dur * ramp.offset(1.0)
    buf = decode_segment(src, t_in, span, 1.0)
    n_out = max(1, int(round(out_dur * OUT_FPS)))
    if not buf:
        return []
    idx = []
    for k in range(n_out):
        u = k / max(1, n_out - 1)
        pos = ramp.offset(u) / max(1e-9, ramp.offset(1.0)) * (len(buf) - 1)
        idx.append(pos)
    out = []
    for pos in idx:
        i0 = int(pos)
        i1 = min(len(buf) - 1, i0 + 1)
        w = pos - i0
        if w < 1e-3:
            out.append(buf[i0].copy())
        else:
            out.append((buf[i0].astype(np.float32) * (1 - w)
                        + buf[i1].astype(np.float32) * w).astype(np.uint8))
    return out


def whip_frame(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """One frame of a whip: both shots pushed sideways, blurred, criss-crossed.

    A whip is not a cut with blur on it. The outgoing frame leaves one way, the
    incoming frame arrives from the other, and for one or two frames they occupy
    the same frame. Motion blur peaks in the middle and falls off at both ends.
    """
    shift = int(OUT_W * 0.55 * k)
    strength = 1.0 - abs(2.0 * k - 1.0)              # 0 at the ends, 1 in the middle
    ca = np.roll(a, -shift, axis=1)
    cb = np.roll(b, OUT_W - shift, axis=1)
    out = ca.astype(np.float32) * (1.0 - k) + cb.astype(np.float32) * k

    radius = int(round(26 * strength))
    if radius >= 2:
        # horizontal box blur, two passes, via cumulative sums — cheap and it
        # smears along the direction of travel, which is the point
        pad = np.pad(out, ((0, 0), (radius, radius), (0, 0)), mode="edge")
        for _ in range(2):
            cs = np.cumsum(pad, axis=1)
            cs = np.concatenate([np.zeros_like(cs[:, :1]), cs], axis=1)
            # box sum of exactly 2*radius samples, anchored at each pixel
            blurred = (cs[:, 2 * radius:] - cs[:, :-2 * radius]) / (2 * radius)
            pad = blurred
        out = pad
    if out.shape[1] != OUT_W:                     # keep the frame size exact
        fixed = np.empty((out.shape[0], OUT_W, 3), dtype=np.float32)
        n = min(OUT_W, out.shape[1])
        off = (out.shape[1] - n) // 2
        fixed[:, :n] = out[:, off:off + n]
        fixed[:, n:] = out[:, off + n - 1: off + n]
        out = fixed
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# script (the words on screen)
# --------------------------------------------------------------------------
@dataclass
class ScriptCard:
    beat: float
    text: str
    accent: str = ""
    matte: bool | None = None      # None = let the renderer decide
    pin: bool = False              # follow the subject instead of the centre

    @property
    def key(self) -> str:
        return f"{self.beat:g}:{self.text}"


def card_time(beat: float, bpm: float) -> float:
    """Seconds from frame one for a script card written at `beat`.

    The contract, in one place because it was wrong once: a script's beats are
    RELATIVE to frame one, and frame one already sits on the track's grid.
    """
    return beat * 60.0 / bpm


def load_script(path: str | Path | None) -> list[ScriptCard]:
    if not path or not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get("cards", [])
    cards = []
    for d in data:
        if isinstance(d, str):
            cards.append(ScriptCard(0.0, d))
        else:
            cards.append(ScriptCard(float(d.get("beat", 0)),
                                    str(d.get("text", "")),
                                    str(d.get("accent", "")),
                                    d.get("matte"),
                                    bool(d.get("pin", False))))
    cards.sort(key=lambda c: c.beat)
    return cards


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def render(plan: Plan, source_path: str, track_path: str, out_path: str | Path,
           script_path: str | Path | None = None, cards_until: float | None = None,
           progress=print, preset: str = "medium", crf: int = 18,
           sfx: bool = True) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grid = plan.grid
    cards = load_script(script_path)
    period = 60.0 / grid.bpm

    # pre-render every card once
    rendered: list[tuple[float, Card, float]] = []
    # Script beats are RELATIVE to frame one, because that is what someone
    # writing a card list means by "beat 28". The first cut already sits on the
    # grid, so beat 0 is exactly 0.000s and every card inherits the track's grid.
    for c in cards:
        t = card_time(c.beat, grid.bpm)
        if t < -0.001:
            continue
        # hold: capped by the act's own cut length, so a card cannot outlive the
        # shot it sits on. In the drop a card lives about one cut.
        cut = next((k for k in plan.cuts
                    if k.out_start - 1e-6 <= t < k.out_end), None)
        hold = 2.4
        if cut is not None:
            hold = min(0.80 if cut.act == "drop" else 2.4, max(cut.dur * 1.6, 0.30))
        from . import fonts as _fonts

        rendered.append((t, render_card(c.text, OUT_W, OUT_H,
                                        accent=c.accent or None,
                                        cap_frac=_fonts.cap_frac()), hold))
    rendered.sort(key=lambda r: r[0])

    # Matte is a statement, so it goes on a minority of drop cards: every fourth
    # one, unless the script asked for it explicitly.
    matte_for = {}
    n_seen = 0
    for ti, (ct, _c, _h) in enumerate(rendered):
        explicit = cards[ti].matte if ti < len(cards) else None
        if explicit is not None:
            matte_for[ti] = bool(explicit)
        else:
            matte_for[ti] = (n_seen % 4 == 2)
        n_seen += 1

    def pinned_active(ti: int, cut) -> bool:
        """Is a card that wants tracking on screen during this cut?"""
        if ti >= len(cards) or not cards[ti].pin:
            return False
        ct, _c, hold = rendered[ti]
        return ct - 1e-6 < cut.out_end and ct + hold > cut.out_start

    total_frames = int(round(plan.duration * OUT_FPS))
    enc = subprocess.Popen(
        [ffmpeg(), "-nostdin", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{OUT_W}x{OUT_H}", "-r", str(OUT_FPS), "-i", "-",
         "-an", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
         "-pix_fmt", "yuv420p", str(out_path.with_suffix(".video.mp4"))],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    written = 0
    prev_last: np.ndarray | None = None
    for ci, cut in enumerate(plan.cuts):
        g = plan.grade_for(cut.act)
        if cut.ramp:
            frames = decode_ramped(source_path, cut.src_in, cut.dur,
                                   make_ramp(cut.ramp))
        else:
            frames = decode_segment(source_path, cut.src_in, cut.src_dur, cut.speed)

        # A pinned card follows the subject, so the cut needs a track before the
        # compositor can draw. Tracking costs ~0.15s per cut and is skipped
        # entirely when no card is pinned.
        track = None
        if len(frames) > 1 and any(pinned_active(t, cut) for t in range(len(rendered))):
            found = track_box(frames)
            # No face in the seed frame is normal (a wide shot, a back, a stunt).
            # The card falls back to centred rather than the cut failing.
            if found is not None:
                track = smooth(found)

        want = max(1, int(round(cut.dur * OUT_FPS)))
        if len(frames) < want:
            # A short decode is a seek problem, not a stylistic choice: retry the
            # cut once with a little lead-in before the in-point. Padding with
            # black (the previous behaviour) hid a dead cut inside a render that
            # otherwise looked fine.
            frames = decode_segment(source_path, max(0.0, cut.src_in - 0.20),
                                    cut.src_dur + 0.20, cut.speed)
        if not frames:
            raise RuntimeError(
                f"cut {cut.index}: decoded no frames from {source_path} at "
                f"{cut.src_in:.3f}s (+{cut.src_dur:.3f}s). Refusing to write "
                f"black frames.")
        while len(frames) < want:
            frames.append(frames[-1])
        for fi in range(want):
            t = cut.out_start + fi / OUT_FPS
            frame = grade(frames[fi], g)

            # whip: the first frames of a marked cut are shared with the shot
            # before it, which is what makes two shots feel like one move
            if cut.transition == "whip" and prev_last is not None and fi < 2:
                frame = whip_frame(prev_last, frame, 0.62 if fi == 0 else 0.88)

            # flash: the first two frames of a marked cut
            if cut.flash and fi < 2:
                k = 0.85 if fi == 0 else 0.55
                frame = (frame.astype(np.float32) * (1 - k) + 255.0 * k).astype(np.uint8)

            # type
            for ti, (ct, card, hold) in enumerate(rendered):
                nxt = rendered[ti + 1][0] if ti + 1 < len(rendered) else 1e9
                if ct - 1e-6 <= t < min(nxt, ct + hold) - 1e-6:
                    if cards_until is not None and t > cards_until:
                        break
                    age = t - ct
                    # Track first, then light: a pinned card MOVES, so a halo
                    # measured at the pinned card's start position is left behind
                    # as a ghost of the word on a bright plate.
                    if cards[ti].pin and track is not None:
                        pt = track.at(fi)
                        if pt is not None:
                            card = card.moved_to(pt[0], pt[1] - card.rgba.shape[0] * 0.15,
                                                 OUT_W, OUT_H)
                    # Scrim when the plate behind the TYPE is bright, measured
                    # under the glyphs and at the 90th percentile — a mean is
                    # fooled by a dark shirt filling half the card's box, which
                    # is exactly the shot where a white word disappears.
                    reg = frame[max(0, card.y):card.y + card.rgba.shape[0],
                                max(0, card.x):card.x + card.rgba.shape[1]]
                    if reg.size:
                        lum = reg.mean(axis=2) if reg.ndim == 3 else reg
                        mask = card.rgba[..., 3] > 40
                        if mask.shape == lum.shape and mask.any():
                            vals = lum[mask]
                        else:
                            vals = lum.reshape(-1)
                        plate = float(np.percentile(vals, 90))
                        amt = max(0.0, min(0.52, (plate - 78.0) / 90.0 * 0.52))
                        if amt > 0.01:
                            # a bright plate needs a tight halo, or the glow
                            # smears across the face instead of hugging the type
                            scrim(frame, card, amount=amt,
                                  blur=22 if amt < 0.24 else 9)
                    use_matte = matte_for[ti]
                    if use_matte and cut.act == "drop":
                        composite_matte(frame, card)
                    elif age < 2.0 / OUT_FPS:
                        composite(frame, card.scaled(1.05), alpha=0.7)
                    else:
                        composite(frame, card, alpha=1.0)
                    break

            prev_last = frame
            enc.stdin.write(frame.tobytes())
            written += 1
            if written % 60 == 0:
                progress(f"  frame {written}/{total_frames}")

    enc.stdin.close()
    err = enc.stderr.read().decode()[-800:]
    enc.wait()
    if err.strip():
        progress(err)

    # ---- sound: track shaped by act, cut to the picture's length ----
    audio = _sound(plan, track_path, out_path.with_suffix(".audio.wav"),
                   sfx=sfx)

    final = out_path
    subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-y",
         "-i", str(out_path.with_suffix(".video.mp4")),
         "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(final)], check=True)
    for p in (out_path.with_suffix(".video.mp4"), audio,
              audio.with_suffix(".wav")):
        try:
            p.unlink()
        except OSError:
            pass
    return final


def _sound(plan: Plan, track_path: str, out_wav: Path,
           sfx: bool = True) -> Path:
    """Track from plan.start, gain-shaped per act, loudness-normalised."""
    x = load_audio(track_path)
    a = max(0, int(round(plan.start * SR)))
    b = min(len(x), a + int(plan.duration * SR))
    seg = x[a:b].astype(np.float32)

    gain = np.ones(len(seg), dtype=np.float32)
    for cut in plan.cuts:
        i0 = int(cut.out_start * SR)
        i1 = min(len(seg), int(cut.out_end * SR))
        if i1 <= i0:
            continue
        gain[i0:i1] = ACT_GAIN.get(cut.act, 0.8)
    # smooth the gain steps over 120ms so an act change is a swell, not a click
    k = int(0.12 * SR)
    if k > 1 and len(gain) > k:
        pad = np.pad(gain, (k // 2, k // 2), mode="edge")
        gain = np.convolve(pad, np.ones(k) / k, mode="valid")[: len(gain)]
    seg = seg * gain

    if sfx:
        cues = cues_for(plan)
        bed = render_cues(cues, plan.duration)
        # the track is the score; the design sits under it and never masks it
        n = min(len(seg), len(bed))
        seg[:n] = np.clip(seg[:n] + bed[:n], -1.0, 1.0)

    import wave
    pcm = (np.clip(seg, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    # normalise to the campaign loudness target so platform gain is predictable
    norm = out_wav.with_suffix(".norm.wav")
    subprocess.run(
        [ffmpeg(), "-nostdin", "-v", "error", "-y", "-i", str(out_wav),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", str(norm)],
        check=True)
    return norm


def main(argv=None):
    import argparse

    from .grid import analyse as analyse_track
    from .plan import build_plan, summarise
    from .shots import analyse as analyse_source

    ap = argparse.ArgumentParser(description="render an overedit from a plan")
    ap.add_argument("--plan", default=None, help="plan json (else build one)")
    ap.add_argument("--track", required=False)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", default=None)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    if a.plan:
        grid = analyse_track(a.track) if a.track else None
        raise SystemExit("--plan loading is done by produce.py; use that")
    grid = analyse_track(a.track, a.end)
    src = analyse_source(a.source, a.end)
    plan = build_plan(grid, src, a.start, a.end, a.seed)
    print(summarise(plan))
    out = render(plan, a.source, a.track, a.out, a.script)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
