#!/usr/bin/env python3
"""Sound design we own outright: a bed and hits, synthesised, not licensed.

The user's position was "no one needs rights for a music bed, all that matters
is views". The honest reply is not a lecture - it is that unlicensed music is a
*views* problem: Content ID mutes the post or swaps the audio, some regions get
blocked outright, and repeats get the account restricted. A bed that survives
all of that is one nobody can claim.

So this module makes the bed instead of licensing it. Every sample is a sine,
a triangle or filtered noise generated here, which means:

* no third-party master recording, so no Content ID match, no claim, no mute;
* no licence to expire or territory to exclude;
* it can be re-tuned per campaign (tempo, key, level) without re-licensing.

Musically it is deliberately plain - an A-minor pad, a soft sub on the beat, a
slow tremolo - because the job of a bed under speech is to remove the "recorded
in a bedroom" silence, not to be listened to. The gate enforces that: `qc_gate`
fails a render where the voice does not sit at least 12 dB over the bed.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

RATE = 48000
BPM = 84.0
#: A minor, low and open: A2, C3, E3, A3.
CHORD = (110.00, 130.81, 164.81, 220.00)

#: The bed sits this far under the voice once the gate is measured on the
#: finished file. Measured, not assumed - see `bed_level_check`.
#: Measured on the finished file, not on the synth output: the first pass at
#: 0.022 landed at -24.9 dBFS in the quiet moments of post 7 - a pad you can
#: hear thinking - because the loudness pass and the stereo sum both lift it.
#: 0.012 puts the gaps near -30 dBFS, which is felt but not listened to.
BED_RMS = 0.012
DUCK = 0.30              # bed level while someone is talking


def synth_bed(seconds: float, rate: int = RATE, *, bpm: float = BPM,
              chord: tuple[float, ...] = CHORD, seed: int = 7) -> np.ndarray:
    """A slow pad plus a soft pulse. Returns float32 (n, 2) in [-1, 1]."""
    n = max(1, int(round(seconds * rate)))
    t = np.arange(n, dtype=np.float32) / rate
    rng = np.random.default_rng(seed)

    pad = np.zeros(n, dtype=np.float32)
    for i, f in enumerate(chord):
        # two slightly detuned voices per note: the beating is what stops a
        # synth pad sounding like a test tone
        for det, amp in ((0.0, 1.0), (0.6 + 0.2 * i, 0.55)):
            w = 2.0 * math.pi * (f + det * 0.11) * t + rng.uniform(0, 6.28)
            pad += (amp / len(chord)) * np.sin(w).astype(np.float32)

    # one-pole lowpass: takes the edge off, keeps it out of the voice's band
    a = 0.10
    for _ in range(2):
        pad = _one_pole(pad, a)

    # slow breathing, so 20 seconds of pad does not read as a stuck note
    pad *= (0.82 + 0.18 * np.sin(2 * math.pi * 0.055 * t)).astype(np.float32)

    # sub pulse on the beat: felt more than heard, and only on 1 and 3
    beat = 60.0 / bpm
    pulse = np.zeros(n, dtype=np.float32)
    k = 0
    while k * beat < seconds:
        if k % 4 in (0, 2):
            start = int(k * beat * rate)
            length = min(n - start, int(0.28 * rate))
            if length > 0:
                tt = np.arange(length, dtype=np.float32) / rate
                env = np.exp(-tt / 0.085).astype(np.float32)
                pulse[start:start + length] += 0.55 * env * np.sin(
                    2 * math.pi * 55.0 * tt).astype(np.float32)
        k += 1

    mono = 0.75 * pad + 0.25 * pulse
    # gentle stereo: the two sides drift a few samples apart
    left = mono
    right = np.roll(mono, int(0.004 * rate))
    out = np.stack([left, right], axis=1)
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak * 0.5).astype(np.float32)


def _one_pole(x: np.ndarray, a: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (float(x[i]) - acc)
        y[i] = acc
    return y


def speech_gain(seconds: float, intervals: list[tuple[float, float]], rate: int = RATE,
                *, duck: float = DUCK, attack: float = 0.06,
                release: float = 0.26) -> np.ndarray:
    """Per-sample bed gain: ducked while talking, open in the gaps.

    Computed from the transcript's own word times, so it ducks before the
    voice arrives rather than after a detector notices it. Deterministic, and
    testable without listening.
    """
    n = max(1, int(round(seconds * rate)))
    target = np.ones(n, dtype=np.float32)
    for start, end in intervals:
        i0 = max(0, int(start * rate) - int(attack * rate))
        i1 = min(n, int(end * rate) + int(release * rate))
        if i1 > i0:
            target[i0:i1] = duck
    # smooth the steps so the bed never clicks
    k = max(1, int(0.05 * rate))
    kernel = np.ones(k, dtype=np.float32) / k
    return np.convolve(target, kernel, mode="same").astype(np.float32)


def thump(rate: int = RATE, *, freq: float = 58.0, seconds: float = 0.22,
          level: float = 0.20) -> np.ndarray:
    """A sub hit for the punch-ins: felt on the emphasised word."""
    n = int(seconds * rate)
    t = np.arange(n, dtype=np.float32) / rate
    env = np.exp(-t / 0.055).astype(np.float32)
    body = np.sin(2 * math.pi * freq * t).astype(np.float32)
    click = np.exp(-t / 0.004).astype(np.float32) * 0.15
    return (level * (body * env + click)).astype(np.float32)


def speech_level(audio) -> float:
    """RMS of the speech, not of the file.

    A fixed bed level is the wrong instrument: compress the voice and the bed
    creeps up relative to it, silently. Measuring the speech and placing the
    bed a fixed number of dB under it keeps the relationship stable no matter
    what the voice chain does.
    """
    import numpy as np
    x = np.asarray(audio, dtype=np.float32)
    if not len(x):
        return 0.0
    win = 320                                    # 20 ms at 16 kHz
    n = len(x) // win
    if n < 2:
        return float(np.sqrt((x.astype(np.float64) ** 2).mean()))
    frames = np.sqrt((x[: n * win].reshape(n, win).astype(np.float64) ** 2).mean(axis=1))
    return float(np.percentile(frames, 60))      # speech body, not the peaks


def bed_target(voice_rms: float, *, under_db: float = 18.0) -> float:
    """The bed level that sits `under_db` below the measured voice."""
    return max(1e-5, float(voice_rms) * (10 ** (-under_db / 20.0)))


def tick(rate: int = RATE, *, freq: float = 2400.0, seconds: float = 0.045,
         level: float = 0.05) -> np.ndarray:
    """A very quiet high tick on the strongest words.

    The ear should agree with the eye. It has to be under the voice to be
    pleasant - the gate fails a render whose voice is not 12 dB clear, and
    this sits far below that.
    """
    n = int(seconds * rate)
    t = np.arange(n, dtype=np.float32) / rate
    env = np.exp(-t / 0.010).astype(np.float32)
    return (level * env * np.sin(2 * math.pi * freq * t).astype(np.float32)).astype(np.float32)


def build_track(seconds: float, intervals: list[tuple[float, float]],
                hits: list[float], rate: int = RATE,
                target_rms: float | None = None,
                ticks: list[float] | None = None) -> np.ndarray:
    """Full bed: pad, ducking, and a hit on each punch.

    `target_rms` should come from `bed_target(speech_level(...))` so the bed
    tracks the voice; the constant is only a fallback.
    """
    bed = synth_bed(seconds, rate)
    gain = speech_gain(seconds, intervals, rate)
    bed = bed * gain[:, None]
    # normalise to the target RMS *after* ducking, so the level is what the
    # gate will measure rather than what the raw pad happened to produce
    target = BED_RMS if target_rms is None else float(target_rms)
    rms = float(np.sqrt(np.mean(bed.astype(np.float64) ** 2))) or 1.0
    bed = (bed * (target / rms)).astype(np.float32)
    # fade in under the first word and out with the picture: a bed that stops
    # dead at the last frame sounds like the file was cut, not ended
    fin = min(n_bed := len(bed), int(0.45 * rate))
    bed[:fin] *= np.linspace(0.0, 1.0, fin, dtype=np.float32)[:, None]
    fout = min(n_bed, int(0.8 * rate))
    bed[n_bed - fout:] *= np.linspace(1.0, 0.0, fout, dtype=np.float32)[:, None]
    hit = thump(rate)
    for at in hits:
        i0 = int(at * rate)
        i1 = min(len(bed), i0 + len(hit))
        if i1 > i0:
            bed[i0:i1] += hit[: i1 - i0, None]
    tk = tick(rate)
    for at in ticks or []:
        i0 = int(at * rate)
        i1 = min(len(bed), i0 + len(tk))
        if i1 > i0:
            bed[i0:i1] += tk[: i1 - i0, None]
    return np.clip(bed, -0.99, 0.99)


def write_wav(path: Path, audio: np.ndarray, rate: int = RATE) -> Path:
    import wave
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(audio.shape[1] if audio.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def mix_into(video: Path, out: Path, audio: np.ndarray, rate: int = RATE,
             ffmpeg_bin: str = "ffmpeg") -> Path:
    """Add the bed under the existing mix, video untouched (stream copy)."""
    with tempfile.TemporaryDirectory() as td:
        wav = write_wav(Path(td) / "bed.wav", audio, rate)
        subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(video), "-i", str(wav),
             "-filter_complex",
             "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v:0", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)], check=True)
    return out


def word_intervals(words: list[dict]) -> list[tuple[float, float]]:
    """(start, end) pairs from the manifest's kept words."""
    out = []
    for w in words:
        s, e = float(w.get("at", 0.0)), float(w.get("end", 0.0))
        if e > s:
            out.append((s, e))
    return sorted(out)
