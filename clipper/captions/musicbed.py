"""Synthesized music beds for the next-level format.

The reference shorts all run a constant bed under the voice (~-14 LUFS
total). Ours are generated, not downloaded: slow chord pads from summed
sines with soft attacks - three moods, perfectly loopable, CC0 (see
assets/sfx/LICENSES.md). Regenerate with:  python -m clipper.captions.musicbed
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .. import config

SAMPLE_RATE = 48000
BED_DIR = config.ROOT / "assets" / "music"

# chord progressions as (root_midi, [semitone offsets]) - 4 s per chord,
# two passes = a 32 s seamless loop
MOODS: dict[str, list[tuple[int, list[int]]]] = {
    # dark tension: Am - F - C - G with added 9ths
    "dark": [(45, [0, 3, 7, 14]), (41, [0, 3, 7, 14]),
             (48, [0, 4, 7, 14]), (43, [0, 4, 7, 14])],
    # bright explainer: C - G - Am - F major
    "bright": [(48, [0, 4, 7, 11]), (43, [0, 4, 7, 11]),
               (45, [0, 3, 7, 10]), (41, [0, 4, 7, 11])],
    # chill maj7: Cmaj7 - Am7 - Fmaj7 - G6
    "chill": [(48, [0, 4, 7, 11]), (45, [0, 3, 7, 10]),
              (41, [0, 4, 7, 11]), (43, [0, 4, 7, 9])],
}

CHORD_S = 4.0
PASSES = 2


def _freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def _chord_pcm(root: int, offsets: list[int], seconds: float) -> list[float]:
    n = int(SAMPLE_RATE * seconds)
    out = [0.0] * n
    freqs = [_freq(root), _freq(root - 12)] + [_freq(root + o) for o in offsets]
    amps = [0.30, 0.22] + [0.16] * len(offsets)
    for f, a in zip(freqs, amps):
        # two slightly detuned voices per note: a pad, not a beep
        for detune in (1.0, 1.003):
            phase = 0.0
            step = 2 * math.pi * f * detune / SAMPLE_RATE
            for i in range(n):
                out[i] += a * 0.5 * math.sin(phase)
                phase += step
    # slow swell inside every chord keeps the bed breathing
    for i in range(n):
        t = i / n
        swell = 0.82 + 0.18 * math.sin(2 * math.pi * t - math.pi / 2)
        out[i] *= swell
    return out


def _bed_pcm(mood: str) -> bytes:
    chords = MOODS[mood] * PASSES
    n_chord = int(SAMPLE_RATE * CHORD_S)
    fade = int(SAMPLE_RATE * 0.9)  # crossfade chords into each other
    total = n_chord * len(chords)
    mix = [0.0] * (total + fade)
    for ci, (root, offsets) in enumerate(chords):
        seg = _chord_pcm(root, offsets, CHORD_S + fade / SAMPLE_RATE)
        base = ci * n_chord
        for i, v in enumerate(seg):
            if base + i < len(mix):
                mix[base + i] += v
    # the progression repeats identically, so the tail wraps harmonically
    # into the head - under a ducked voice the seam is inaudible
    loop = mix[:total]
    peak = max(abs(v) for v in loop) or 1.0
    gain = 0.42 / peak
    samples = bytearray()
    for v in loop:
        x = max(-0.95, min(0.95, v * gain))
        samples += struct.pack("<h", int(x * 32767))
    return bytes(samples)


def synthesize_beds(out_dir: Path | None = None) -> list[Path]:
    out_dir = Path(out_dir) if out_dir else BED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for mood in MOODS:
        p = out_dir / f"{mood}.wav"
        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(_bed_pcm(mood))
        written.append(p)
    return written


def bed_file(mood: str | None) -> str | None:
    if not mood or str(mood).lower() in ("off", "none", ""):
        return None
    p = BED_DIR / f"{str(mood).lower()}.wav"
    return str(p) if p.exists() else None


if __name__ == "__main__":  # pragma: no cover
    for p in synthesize_beds():
        print(p)
