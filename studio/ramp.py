"""Speed ramps.

A constant-speed shot is the default because it is easy, not because it is
good. On slow-motion footage (a Twixtor pack, a 60fps action plate) the single
biggest upgrade is to *change* the speed inside the shot so it decelerates into
the cut: the frame before the next cut lands becomes slow motion, so the next cut
arrives like an impact instead of just being the next thing.

The ramp is defined in the OUTPUT time domain (u = 0 at the start of the cut,
u = 1 at the end) and maps to a source offset by integrating the speed curve:

    source_offset(u) = out_dur * ∫0..u speed(v) dv

so `speed(u)` is literally "how many seconds of source pass per second of
output" at that moment. Mean speed over the cut is the integral at u = 1, which
is what the planner uses to check the shot is long enough.
"""

from __future__ import annotations

from dataclasses import dataclass

# common shapes, as (from_speed, to_speed, curve)
RAMPS = {
    # decelerate into the cut: the classic punch-in before a hit
    "settle": (1.75, 0.42, 2.4),
    # accelerate out of the cut, so the shot leaves fast
    "launch": (0.55, 1.85, 0.8),
    # gentle drift, for the out act
    "drift": (0.75, 0.45, 1.0),
}


@dataclass(frozen=True)
class Ramp:
    start_speed: float
    end_speed: float
    curve: float = 1.0      # >1 = change happens late, <1 = happens early

    def speed(self, u: float) -> float:
        u = min(1.0, max(0.0, u))
        e = u ** self.curve
        return self.start_speed + (self.end_speed - self.start_speed) * e

    def offset(self, u: float, steps: int = 240) -> float:
        """Normalised source offset in [0, mean_speed]."""
        u = min(1.0, max(0.0, u))
        n = max(1, int(steps * u))
        acc = 0.0
        h = u / n
        for i in range(n):
            acc += self.speed((i + 0.5) * h) * h
        return acc

    @property
    def mean_speed(self) -> float:
        return self.offset(1.0)

    def as_dict(self):
        return {"start_speed": round(self.start_speed, 3),
                "end_speed": round(self.end_speed, 3),
                "curve": self.curve,
                "mean_speed": round(self.mean_speed, 3)}


def make(name: str) -> Ramp:
    a, b, c = RAMPS[name]
    return Ramp(a, b, c)


def mean_speed_of(spec) -> float:
    """Mean speed for a plan's ramp field: a Ramp, a name, or None."""
    if spec is None:
        return 1.0
    if isinstance(spec, Ramp):
        return spec.mean_speed
    if isinstance(spec, str):
        return make(spec).mean_speed
    if isinstance(spec, dict):
        return Ramp(float(spec.get("start_speed", 1.0)),
                    float(spec.get("end_speed", 1.0)),
                    float(spec.get("curve", 1.0))).mean_speed
    return 1.0
