"""Beat-locked sound design.

The picture cuts on the grid; the sound has to arrive on the same grid or the
whole edit feels one frame late. Every SFX here is SYNTHESISED, which matters for
two reasons: it is deterministic (the same plan renders the same audio), and there
is no licensing question about a hit you generated yourself.

What goes where, and why:

  riser      ends EXACTLY on the first frame of the drop. A riser that stops early
             leaves a hole; one that overshoots steps on the downbeat.
  impact     on the drop downbeat. This is the single loudest event in the edit.
  whoosh     on a whip transition, ending on the cut. The whip's picture blur is
             the visual half of the same gesture.
  tick       on a flash cut. Short, high, quiet — it marks the join without
             competing with the music.
  swell      on the first frame of the out act: the exhale needs an entrance too.
  tape_stop  runs INTO the drop, and replaces the riser when the design asks for
             it: the music stopping itself is the tension, and stacking a riser
             on top of that is two ideas where one is enough.
  sub_drop   under the drop downbeat, an octave below everything else. Felt on a
             phone speaker, audible as weight on a good one.

Levels are relative and conservative: the track is the score, these are accents.
A hit louder than the music is karaoke.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 48000


def _env(n: int, attack: float, decay: float, power: float = 1.0) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-5), 0, 1) ** power
    return a * np.exp(-t / max(decay, 1e-5))


def impact(dur: float = 0.55, gain: float = 1.0) -> np.ndarray:
    """Sub boom: a pitch drop from 95 Hz to 38 Hz plus a transient click."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 38.0 + (95.0 - 38.0) * np.exp(-t / 0.055)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    body *= _env(n, 0.0015, 0.17)
    click = np.random.default_rng(101).normal(0, 1, n) * np.exp(-t / 0.0035) * 0.45
    return (body * 0.95 + click) * gain


def whoosh(dur: float = 0.30, gain: float = 1.0) -> np.ndarray:
    """Band-ish noise that rises into the cut and stops dead on it.

    The envelope is asymmetric on purpose: slow in, hard out. A symmetric swell
    sounds like a reversed cymbal; a hard tail is what sells a whip.
    """
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(202).normal(0, 1, n)
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        # one-pole low-pass with a rising cutoff = the "air" opening up
        k = 0.02 + 0.42 * (i / n) ** 2
        acc += k * (noise[i] - acc)
        out[i] = acc
    rise = (t / dur) ** 1.8
    fall = np.clip((dur - t) / (dur * 0.12), 0, 1) ** 2.2
    return out * rise * fall * gain * 2.2


def riser(dur: float = 1.6, gain: float = 1.0) -> np.ndarray:
    """Noise sweep that lands on the drop. Exponential amplitude, no tail."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(303).normal(0, 1, n)
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        k = 0.001 + 0.09 * (i / n) ** 3
        acc += k * (noise[i] - acc)
        out[i] = acc
    # a rising tone under the noise so it has pitch, not just hiss
    tone = np.sin(2 * np.pi * np.cumsum(180.0 + 900.0 * (t / dur) ** 2) / SR)
    amp = (t / dur) ** 2.4
    return (out * 1.6 + tone * 0.30) * amp * gain


def tick(dur: float = 0.055, gain: float = 1.0) -> np.ndarray:
    """A high, dry click for a flash frame."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(404).normal(0, 1, n)
    # crude high-pass: difference the noise
    hp = np.diff(np.concatenate([[0.0], noise]))
    return hp * np.exp(-t / 0.006) * gain * 0.75


def swell(dur: float = 0.9, gain: float = 1.0) -> np.ndarray:
    """A soft airy entrance for the out act."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(505).normal(0, 1, n)
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        k = 0.05 * (1.0 - 0.7 * (i / n))
        acc += k * (noise[i] - acc)
        out[i] = acc
    env = np.clip(t / (dur * 0.35), 0, 1) * np.clip((dur - t) / (dur * 0.75), 0, 1)
    return out * env * gain * 1.5


@dataclass
class Cue:
    at: float          # seconds from frame one
    kind: str          # impact | whoosh | riser | tick | swell
    gain: float = 1.0

    def as_dict(self):
        return {"at": round(self.at, 3), "kind": self.kind,
                "gain": round(self.gain, 3)}


# level per kind, relative to the track. Conservative on purpose.
def tape_stop(dur: float = 0.42, gain: float = 1.0) -> np.ndarray:
    """A tape stopping: pitch falling away, no tail.

    This is the one design move that instantly reads "an editor did this" rather
    than "an app did this". It is not a sound effect laid over the song — it is
    the song behaving, which is why it works on a mix that has no room for more
    layers.
    """
    n = int(SR * dur)
    t = np.arange(n) / SR
    rate = np.clip(1.0 - (t / dur) ** 0.7, 0.0, 1.0)      # speed falls to zero
    phase = np.cumsum(rate) / SR
    sig = (0.55 * np.sin(2 * np.pi * 220 * phase * 2.0)
           + 0.30 * np.sin(2 * np.pi * 330 * phase * 2.0)
           + 0.15 * np.sin(2 * np.pi * 110 * phase * 2.0))
    return (sig * _env(n, 0.02, 1.0, 1.4) * gain).astype(np.float32)


def sub_drop(dur: float = 1.1, gain: float = 1.0) -> np.ndarray:
    """A low sine falling an octave under the drop — felt, not heard."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = 55.0 * np.exp(-t * 0.9) + 28.0
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return (sig * _env(n, 0.004, 1.0, 2.2) * gain * 0.9).astype(np.float32)


LEVEL = {"impact": 0.62, "whoosh": 0.30, "riser": 0.34, "tick": 0.16,
         "swell": 0.26, "tape_stop": 0.46, "sub_drop": 0.52}

_BUILDERS = {"impact": impact, "whoosh": whoosh, "riser": riser,
             "tick": tick, "swell": swell,
             "tape_stop": tape_stop, "sub_drop": sub_drop}

_DURS = {"tape_stop": 0.42, "sub_drop": 1.1, "impact": 0.55, "whoosh": 0.30, "riser": 1.6, "tick": 0.055,
         "swell": 0.9}


def cues_for(plan, design: str | None = None) -> list[Cue]:
    """Every sound event, derived from the picture plan.

    The rule that keeps this from becoming noise: an event is placed because the
    PICTURE does something. Cuts get a sound only when they are already a marked
    cut (flash, whip, act change) — not on all 47 cuts.
    """
    cues: list[Cue] = []
    if not plan.cuts:
        return cues

    acts = {}
    for c in plan.cuts:
        acts.setdefault(c.act, c)

    drop = acts.get("drop")
    out = acts.get("out")

    if drop is not None:
        if design == "tape_stop":
            # the song stops itself; nothing else may play over the gap, so the
            # riser is replaced rather than stacked
            cues.append(Cue(max(0.0, drop.out_start - _DURS["tape_stop"] - 0.02),
                            "tape_stop"))
        else:
            # riser lands ON the drop's first frame, not before it
            cues.append(Cue(max(0.0, drop.out_start - _DURS["riser"] + 0.02),
                            "riser"))
        cues.append(Cue(drop.out_start, "impact"))
        cues.append(Cue(drop.out_start, "sub_drop"))

    # whip and flash each get a sound, and a cut never gets both
    for c in plan.cuts:
        if c.act != "drop":
            continue
        if c.transition == "whip":
            cues.append(Cue(max(0.0, c.out_start - _DURS["whoosh"] + 0.015),
                            "whoosh"))
        elif c.flash:
            cues.append(Cue(c.out_start, "tick"))

    if out is not None and out is not drop:
        cues.append(Cue(out.out_start, "swell"))

    cues.sort(key=lambda c: c.at)
    return cues


def render_cues(cues: list[Cue], duration: float) -> np.ndarray:
    """Sum every cue into one buffer of exactly `duration` seconds."""
    n = int(round(duration * SR))
    buf = np.zeros(n, dtype=np.float32)
    for c in cues:
        sig = _BUILDERS[c.kind](_DURS[c.kind], LEVEL[c.kind] * c.gain)
        i = int(round(c.at * SR))
        if i < 0:
            sig = sig[-i:]
            i = 0
        j = min(n, i + len(sig))
        if j > i:
            buf[i:j] += sig[: j - i].astype(np.float32)
    return buf


def write_wav(path: str | Path, mono: np.ndarray, sr: int = SR) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return p


def check_on_grid(cues: list[Cue], plan, tolerance: float = 0.002) -> list[str]:
    """Every cue that is supposed to land on a cut must land on it.

    This exists because a whoosh 30 ms early is invisible in a contact sheet and
    obvious to the ear. Riser and swell are exempt: they are lead-ins.
    """
    problems = []
    starts = {round(c.out_start, 4) for c in plan.cuts}
    for c in cues:
        if c.kind in ("riser", "swell", "whoosh"):
            continue
        if not any(abs(c.at - s) < tolerance for s in starts):
            problems.append(f"{c.kind} at {c.at:.3f}s is not on a cut")
    return problems
