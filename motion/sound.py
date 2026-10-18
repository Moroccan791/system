#!/usr/bin/env python3
"""Stage C sound design for the motion pipeline (Part 3).

Every graphic event in the timeline gets a sound on its EXACT frame:
item entries pop, poster/card words type (soft keystrokes, flag-gated),
counters tick and land on the spoken word, panel rows step in, and
every cut gets a riser ending in an impact on the cut frame (with an
80-150 ms bed dip before the big ones). Variants rotate with seeded
pitch (+-3%) and volume (+-10%) jitter so nothing sounds stamped-on.
A sub-bass bed (20-150 Hz) sits ~24 dB under the voice and a generated
pad loop ducks 12 dB under speech. Final mix: voice loudest, SFX
6-10 dB under it, normalised to -14 LUFS / true peak < -1 dBTP.

All sounds are SYNTHESISED here from oscillators and filtered noise:
original, public-domain (CC0) by construction - see SOUND_LICENSE.md.
No audio files are downloaded or shipped.

Usage:
  python motion/sound.py <timeline_fx.json> <final.mp4> <out.mp4>
      [--typing-sound on|off] [--seed 7]
Writes <out>.sound.json (every event: frame, type, variant, gain)
and prints the Stage-C QC block.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipper.ffmpeg import ffmpeg_exe, probe  # noqa: E402

SR = 48000


# ------------------------------------------------------------- synthesis
def _env(n, attack=0.004, decay_pow=2.0):
    t = np.linspace(0, 1, n, dtype=np.float32)
    a = max(1, int(attack * SR))
    e = (1 - t) ** decay_pow
    e[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    return e


def _peak(x: np.ndarray, target: float = 0.9) -> np.ndarray:
    p = float(np.max(np.abs(x))) + 1e-9
    return (x * (target / p)).astype(np.float32)


def synth(kind: str, rng: np.random.Generator) -> np.ndarray:
    """One mono float32 sample; variant = jittered parameters.
    Every sample is peak-normalised: per-kind gain_db does the mixing,
    so a whoosh and an impact start from the same ceiling."""
    return _peak(_synth_raw(kind, rng))


def _synth_raw(kind: str, rng: np.random.Generator) -> np.ndarray:
    if kind == "key":                      # mechanical keyboard switch
        # A real switch strike, modelled: broadband transient (keycap
        # hit), a low "thock" knock from the case, a faint plate ring.
        # Three switch profiles (deep linear / tactile / clicky) are
        # picked per keystroke so typing never sounds like one sample
        # looped. All synthesised - CC0 by construction.
        n = int(0.12 * SR)
        t = (np.arange(n) / SR).astype(np.float32)
        profile = rng.choice(3, p=[0.5, 0.3, 0.2])
        f0 = (rng.uniform(160, 230), rng.uniform(280, 380),
              rng.uniform(220, 300))[profile]
        noise = rng.standard_normal(n).astype(np.float32)
        k = max(2, int(0.004 * SR))
        hp = noise - np.convolve(noise, np.ones(k, np.float32) / k, "same")
        trans = hp * np.exp(-t / 0.006)                    # ~6 ms hit
        f = f0 * (1 - 0.25 * (1 - np.exp(-t / 0.01)))      # knock, pitch sag
        knock = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.016)
        ring = np.sin(2 * np.pi * rng.uniform(1100, 1600) * t) \
            * np.exp(-t / 0.010)
        out = 0.85 * trans + 0.55 * knock + 0.10 * ring
        if profile == 2:                                   # clicky switch:
            d = int(rng.uniform(0.008, 0.016) * SR)        # click-bar snap
            snap = np.zeros(n, np.float32)
            snap[d:] = hp[:n - d] * np.exp(-t[:n - d] / 0.004)
            out = out + 0.6 * snap
        return out.astype(np.float32) * _env(n, 0.0005, 2.0)
    if kind == "pop":                      # soft UI pop, pitch drop
        n = int(0.10 * SR)
        f = np.linspace(rng.uniform(540, 660), rng.uniform(150, 210), n)
        ph = np.cumsum(f) / SR
        return np.sin(2 * np.pi * ph).astype(np.float32) * _env(n, 0.002)
    if kind == "pop_low":
        n = int(0.13 * SR)
        f = np.linspace(rng.uniform(300, 380), rng.uniform(90, 130), n)
        ph = np.cumsum(f) / SR
        return np.sin(2 * np.pi * ph).astype(np.float32) * _env(n, 0.002)
    if kind == "tick":                     # counter tick
        n = int(0.035 * SR)
        tone = np.sin(2 * np.pi * rng.uniform(1900, 2300)
                      * np.arange(n) / SR).astype(np.float32)
        return tone * _env(n, 0.001, 2.5)
    if kind == "land":                     # counter landing thock
        n = int(0.20 * SR)
        f = np.linspace(210, 68, n)
        ph = np.cumsum(f) / SR
        body = np.sin(2 * np.pi * ph).astype(np.float32)
        click = rng.standard_normal(int(0.008 * SR)).astype(np.float32)
        out = body * _env(n, 0.001, 1.6)
        out[:len(click)] += 0.5 * click
        return out
    if kind == "whoosh":
        n = int(rng.uniform(0.18, 0.26) * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        k = max(3, int(0.006 * SR))
        smooth = np.convolve(noise, np.ones(k, np.float32) / k, "same")
        sweep = np.linspace(0.25, 1.0, n, dtype=np.float32) ** 2
        return (smooth * sweep * _env(n, 0.05, 1.2)).astype(np.float32)
    if kind == "riser":                    # 0.45 s build into the cut
        n = int(0.45 * SR)
        f = np.linspace(160, 1400, n)
        ph = np.cumsum(f) / SR
        tone = np.sin(2 * np.pi * ph).astype(np.float32)
        noise = rng.standard_normal(n).astype(np.float32)
        k = max(3, int(0.004 * SR))
        noise = np.convolve(noise, np.ones(k, np.float32) / k, "same")
        amp = np.linspace(0.05, 1.0, n, dtype=np.float32) ** 2
        return (0.6 * tone + 0.4 * noise) * amp
    if kind == "impact":                   # boom ON the cut frame
        n = int(0.32 * SR)
        f = np.linspace(130, 38, n)
        ph = np.cumsum(f) / SR
        body = np.sin(2 * np.pi * ph).astype(np.float32) * _env(n, 0.001, 1.4)
        noise = rng.standard_normal(int(0.05 * SR)).astype(np.float32)
        body[:len(noise)] += 0.6 * noise * _env(len(noise), 0.001, 2.0)
        return body
    if kind == "snap":                     # small cut accent
        n = int(0.09 * SR)
        body = np.sin(2 * np.pi * np.cumsum(
            np.linspace(300, 90, n)) / SR).astype(np.float32)
        return body * _env(n, 0.001, 2.0)
    if kind == "swipe":                    # exit slide, kept faint
        n = int(0.14 * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        k = max(3, int(0.008 * SR))
        smooth = np.convolve(noise, np.ones(k, np.float32) / k, "same")
        sweep = (1 - np.linspace(0, 1, n, dtype=np.float32)) ** 2
        return (smooth * sweep * _env(n, 0.03, 1.5)).astype(np.float32)
    raise ValueError(kind)


def pitch_jitter(x: np.ndarray, factor: float) -> np.ndarray:
    if abs(factor - 1.0) < 1e-4:
        return x
    idx = np.arange(0, len(x) / factor)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


# ---------------------------------------------------------------- events
def build_events(tl: dict, cuts: list[dict], typing: bool,
                 rng: np.random.Generator) -> list[dict]:
    """Frame-exact event list from the timeline (fps from the video)."""
    ev = []

    def add(t, kind, gain_db, note=""):
        ev.append({"t": round(float(t), 3), "kind": kind,
                   "gain_db": round(float(gain_db), 2), "note": note})

    for it in tl["items"]:
        ty, at = it["type"], float(it["at"])
        until = float(it.get("until") or at)
        if ty == "poster" or ty == "card":
            add(at, "pop", -3, f"{ty} enter")
            last = None
            for row in it.get("rows") or it.get("lines") or []:
                words = row if isinstance(row, list) else [row]
                for w in words:
                    if not isinstance(w, dict):
                        continue
                    wt = float(w["at"])
                    if typing and (last is None or w.get("kind") == "key"
                                   or wt - last >= 0.45):
                        add(wt, "key", -16, "word")
                    last = wt
        elif ty == "counter":
            dur = float(it.get("countDur") or 0.9)
            for k in range(3):  # short 3-tick roll into the landing
                add(at + k * (dur - 0.15) / 2, "tick", -18 + k, "count")
            add(at + dur, "land", -4, "counter lands on the word")
        elif ty in ("list", "process"):
            add(at, "pop", -5, f"{ty} enter")
            rows = it.get("items") or it.get("steps") or []
            for r in rows:
                add(float(r["at"]), "pop_low", -9, f"{ty} row")
            if until - at > 1.5:
                add(until, "swipe", -20, f"{ty} exit")
        elif ty in ("pip", "broll"):
            add(at, "whoosh", -10, f"{ty} enter")
            add(until, "swipe", -18, f"{ty} exit")
        elif ty == "vector":
            # a scene must not move in silence: full-bleed cuts whoosh in,
            # card panels pop; data scenes tick softly while they build
            full = (it.get("mode") or "card") == "fullbleed"
            add(at, "whoosh" if full else "pop", -10 if full else -6,
                f"scene {it.get('name')} enter")
            if full and until - at >= 1.6:
                for k in (0.45, 0.9):
                    add(at + k, "tick", -22, "scene build")
            add(until, "swipe", -20, "scene exit")
        elif ty == "chip":
            add(at, "pop", -6, "chip enter")
        elif ty == "hook":
            add(at, "impact", -8, "hook slate lands")
            add(until, "swipe", -18, "hook slate clears")
        elif ty == "endcard":
            add(at, "pop_low", -7, "end card sting")
        elif ty == "lowerthird":
            add(at, "pop_low", -9, "lower-third slides in")
            if until - at > 2.0:
                add(until, "swipe", -20, "lower-third exit")
        elif ty == "fx" and it.get("kind") == "opening":
            add(0.0, "whoosh", -14, "opening")
    for c in cuts:
        big = c["kind"] in ("flare", "leak")
        if c["kind"] == "flare":
            add(c["t"] - 0.45, "riser", -12, "riser to cut")
        add(c["t"], "impact" if big else "snap", -5 if big else -9,
            f"cut {c['kind']}")
    ev.sort(key=lambda e: e["t"])
    return ev


# ------------------------------------------------------------------ beds
def sub_bed(n: int, voice_rms: float, rng) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / SR
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.11 * t)
    bed = (np.sin(2 * np.pi * 43 * t) + 0.6 * np.sin(2 * np.pi * 64.5 * t)
           + 0.3 * np.sin(2 * np.pi * 86 * t)).astype(np.float32)
    bed *= lfo
    rms = float(np.sqrt(np.mean(bed ** 2))) + 1e-9
    return bed * (voice_rms * 10 ** (-24 / 20) / rms)


def pad_loop(n: int, voice_rms: float, voice: np.ndarray) -> np.ndarray:
    """Generated Am-F-C-G pad, ducked 12 dB under the voice envelope."""
    chords = [[110.0, 164.8, 261.6], [87.3, 130.8, 220.0],
              [130.8, 196.0, 329.6], [98.0, 146.8, 246.9]]
    t = np.arange(n, dtype=np.float32) / SR
    pad = np.zeros(n, dtype=np.float32)
    seg = 2.0
    for i in range(int(n / SR / seg) + 1):
        ch = chords[i % len(chords)]
        s0, s1 = int(i * seg * SR), min(n, int((i + 1) * seg * SR))
        if s0 >= n:
            break
        tt = t[s0:s1]
        tone = sum(np.sin(2 * np.pi * f * tt) for f in ch)
        tone += 0.4 * sum(np.sin(2 * np.pi * f * 2 * tt) for f in ch)
        fade = np.minimum(1, np.minimum(tt - tt[0], tt[-1] - tt) / 0.6 + 0.2)
        pad[s0:s1] += (tone * fade).astype(np.float32)
    rms = float(np.sqrt(np.mean(pad ** 2))) + 1e-9
    pad *= voice_rms * 10 ** (-17 / 20) / rms
    # ducking: -12 dB where the voice is active (150 ms smoothing)
    win = int(0.05 * SR)
    env = np.sqrt(np.convolve(voice ** 2, np.ones(win, np.float32) / win,
                              "same") + 1e-12)
    k = int(0.15 * SR)
    env = np.convolve(env, np.ones(k, np.float32) / k, "same")
    duck = np.where(env > voice_rms * 0.5, 10 ** (-12 / 20), 1.0)
    return pad * duck.astype(np.float32)


# ------------------------------------------------------------------- i/o
def read_audio(video: Path) -> np.ndarray:
    raw = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(video), "-vn", "-ac", "1",
         "-ar", str(SR), "-f", "f32le", "-"], capture_output=True,
        check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def measure_loudness(video: Path) -> dict:
    proc = subprocess.run(
        [ffmpeg_exe(), "-i", str(video), "-vn", "-af",
         "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    txt = proc.stderr
    blk = txt[txt.rfind("{"):txt.rfind("}") + 1]
    d = json.loads(blk)
    return {"lufs": float(d["input_i"]), "true_peak": float(d["input_tp"])}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tl_path, video, out = Path(args[0]), Path(args[1]), Path(args[2])
    typing = "--typing-sound" not in sys.argv or \
        sys.argv[sys.argv.index("--typing-sound") + 1] != "off"
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) \
        if "--seed" in sys.argv else 7
    rng = np.random.default_rng(seed)
    tl = json.loads(tl_path.read_text())
    fps = probe(video).fps or 30.0
    sidecar = video.with_suffix(".transitions.json")
    cuts = json.loads(sidecar.read_text())["cuts"] \
        if sidecar.exists() else []

    voice = read_audio(video)
    # studio voice chain: strip rumble, add presence where speech
    # intelligibility lives, de-ess if this ffmpeg build has the
    # filter, then broadcast levelling (tame the crest so loudness
    # gain does not have to fight the peaks; voice stays loudest)
    filt = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"],
                          capture_output=True, text=True).stdout
    chain = ("highpass=f=75,"
             "equalizer=f=3400:width_type=o:width=1.1:g=2.5,"
             + ("adeesser," if "adeesser" in filt else "")
             + "acompressor=threshold=0.10:ratio=3:attack=2:release=180:"
               "knee=6")
    proc = subprocess.run(
        [ffmpeg_exe(), "-y", "-v", "error", "-f", "f32le", "-ar", str(SR),
         "-ac", "1", "-i", "-", "-af", chain,
         "-f", "f32le", "-ar", str(SR), "-ac", "1", "-"],
        input=voice.tobytes(), capture_output=True, check=True)
    voice = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    n = len(voice)
    voice_rms = float(np.sqrt(np.mean(voice ** 2))) + 1e-9

    events = build_events(tl, cuts, typing, rng)
    sfx = np.zeros(n, dtype=np.float32)
    variants: dict[str, int] = {}
    for e in events:
        variants[e["kind"]] = variants.get(e["kind"], 0) + 1
        e["variant"] = variants[e["kind"]]
        sample = synth(e["kind"], rng)
        sample = pitch_jitter(sample, float(rng.uniform(0.97, 1.03)))
        gain = 10 ** (e["gain_db"] / 20) * float(rng.uniform(0.90, 1.10))
        s0 = int(round(e["t"] * SR))
        s1 = min(n, s0 + len(sample))
        if s0 < n:
            sfx[s0:s1] += sample[:s1 - s0] * gain
        e["frame"] = int(round(e["t"] * fps))
    # SFX bus: peaks ride 6-10 dB under the voice's own level
    sfx_rms = float(np.sqrt(np.mean(sfx ** 2))) + 1e-9
    sfx *= voice_rms * 10 ** (-8 / 20) / sfx_rms * 0.35

    bed = sub_bed(n, voice_rms, rng)
    pad = pad_loop(n, voice_rms, voice)
    # external music bed (--music FILE): looped to length, ~11 dB
    # under the voice, ducked a further 6 dB while she speaks (same
    # envelope law as the generated pad). At -20 dB the bed was
    # effectively inaudible on a phone and the outro tail was silence.
    # Keep the bed genuinely audible, then fade it with the picture.
    music = None
    if "--music" in sys.argv:
        mpath = Path(sys.argv[sys.argv.index("--music") + 1])
        raw = subprocess.run(
            [ffmpeg_exe(), "-v", "error", "-i", str(mpath), "-vn",
             "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
            capture_output=True, check=True).stdout
        mtrack = np.frombuffer(raw, dtype=np.float32).copy()
        if len(mtrack):
            reps = int(np.ceil(n / len(mtrack)))
            music = np.tile(mtrack, reps)[:n].astype(np.float32)
            mrms = float(np.sqrt(np.mean(music ** 2))) + 1e-9
            music *= voice_rms * 10 ** (-11 / 20) / mrms
            win = int(0.05 * SR)
            env = np.sqrt(np.convolve(voice ** 2,
                                      np.ones(win, np.float32) / win,
                                      "same") + 1e-12)
            k = int(0.15 * SR)
            env = np.convolve(env, np.ones(k, np.float32) / k, "same")
            duck = np.where(env > voice_rms * 0.5, 10 ** (-6 / 20), 1.0)
            music = (music * duck.astype(np.float32)).astype(np.float32)
            # the outro: the bed fades with the picture
            tail = np.arange(n, dtype=np.float32) / SR
            music = (music * np.clip((n / SR - tail) / 0.5, 0.0, 1.0)).astype(
                np.float32)
    # 80-150 ms silence dips in bed+pad before the biggest impacts
    def ramp(bus, s0, s1, g0, g1):
        s0, s1 = max(0, s0), min(n, s1)
        if s1 > s0:
            bus[s0:s1] *= np.linspace(g0, g1, s1 - s0, dtype=np.float32)

    for c in cuts:
        if c["kind"] in ("flare", "leak"):
            for bus in (bed, pad) + ((music,) if music is not None else ()):
                ramp(bus, int((c["t"] - 0.28) * SR),
                     int((c["t"] - 0.13) * SR), 1.0, 0.12)
                ramp(bus, int(c["t"] * SR),
                     int((c["t"] + 0.10) * SR), 0.12, 1.0)
    mix = voice + sfx + bed + pad
    if music is not None:
        mix = (mix + music).astype(np.float32)
    # soft ceiling ~-2.4 dBFS: gain staging happens against a limiter,
    # not against re-encode trims (which used to eat the loudness)
    mix = (0.76 * np.tanh(mix / 0.76)).astype(np.float32)

    wav = out.with_suffix(".mix.wav")

    def write_wav(x: np.ndarray) -> None:
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "f32le",
                        "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a",
                        "pcm_s16le", str(wav)], input=x.tobytes(),
                       check=True)

    write_wav(mix)
    gain_db = -14.0 - measure_loudness(wav)["lufs"]
    mix = (0.76 * np.tanh(mix * 10 ** (gain_db / 20) / 0.76)).astype(
        np.float32)
    write_wav(mix)
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(video),
                    "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", str(out)], check=True)
    wav.unlink()
    for _ in range(2):  # encode drift correction (peaks have headroom)
        cur = measure_loudness(out)
        err = -14.0 - cur["lufs"]
        if abs(err) <= 0.35:
            break
        tmp = out.with_suffix(".g.mp4")
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(out),
                        "-c:v", "copy", "-af", f"volume={err:.2f}dB",
                        "-c:a", "aac", "-b:a", "160k", str(tmp)], check=True)
        tmp.replace(out)

    loud = measure_loudness(out)
    if loud["true_peak"] > -1.05:  # AAC overshoot safety: trim & re-encode
        trim = loud["true_peak"] + 1.7
        tmp = out.with_suffix(".tp.mp4")
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(out),
                        "-c:v", "copy", "-af", f"volume=-{trim:.2f}dB",
                        "-c:a", "aac", "-b:a", "160k", str(tmp)], check=True)
        tmp.replace(out)
        loud = measure_loudness(out)
    # A peak-only trim can move the integral down ~0.8 LU while leaving
    # healthy -1.8 dBTP of headroom. Finish with a TP-aware loudness
    # pass (rather than gain it back and recreate the intersample peak).
    # The +0.5 LU command offset is calibrated to this mono AAC encode:
    # ffmpeg's dynamic loudnorm measured -14.04 LUFS / -1.59 dBTP from a
    # -14.86 LUFS / -1.86 dBTP input in the Whop pilot. Measure again;
    # do not claim PASS if the exact encoded file misses the target.
    for _ in range(2):
        if -14.35 <= loud["lufs"] <= -13.65 and loud["true_peak"] < -1.05:
            break
        target = -13.5 if loud["lufs"] < -14.35 else -14.0
        tmp = out.with_suffix(".norm.mp4")
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(out),
                        "-map", "0:v", "-map", "0:a", "-c:v", "copy",
                        "-af", f"loudnorm=I={target:.1f}:TP=-1.5:LRA=11:linear=false",
                        # loudnorm upsamples internally to 192kHz. Keep
                        # delivery at 48kHz for broad platform support.
                        "-ar", str(SR), "-c:a", "aac", "-b:a", "160k",
                        str(tmp)], check=True)
        tmp.replace(out)
        loud = measure_loudness(out)
    dur = n / SR
    per_sec = len(events) / dur
    texture = sum(1 for e in events if e["kind"] in ("key", "tick"))
    accent_sec = (len(events) - texture) / dur
    cut_frames = {int(round(c["t"] * fps)) for c in cuts}
    impact_frames = {e["frame"] for e in events
                     if e["kind"] in ("impact", "snap")}
    aligned = cut_frames <= impact_frames
    ok = aligned and -14.7 <= loud["lufs"] <= -13.3 \
        and loud["true_peak"] < -1.0 and 0.4 <= accent_sec <= 2.0
    report = {"video": str(out), "seed": seed, "typing_sound": typing,
              "music_bed": str(sys.argv[sys.argv.index("--music") + 1])
              if "--music" in sys.argv else None,
              "voice_chain": chain,
              "events": len(events), "events_per_sec": round(per_sec, 2),
              "accent_events_per_sec": round(accent_sec, 2),
              "by_kind": variants, "cuts_covered": len(cut_frames),
              "impacts_on_cut_frame": aligned,
              "loudness": loud, "events_detail": events}
    out.with_suffix(".sound.json").write_text(json.dumps(report, indent=1))
    print(f"SOUND QC {out.name}: {'PASS' if ok else 'FAIL'}  "
          f"{len(events)} events ({per_sec:.2f}/s total, "
          f"{accent_sec:.2f}/s accents), "
          f"cuts covered {len(cut_frames)}/{len(cuts)}, "
          f"impacts on cut frame: {aligned}, "
          f"{loud['lufs']:.1f} LUFS, TP {loud['true_peak']:.1f} dBTP")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
