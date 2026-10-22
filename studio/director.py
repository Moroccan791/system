"""Direction — the lyric decides the shot, the grid decides the cut rate.

`plan.py` picks shots by score: motion rank, brightness, novelty. That is the
right machine for an edit with no subject, and the wrong one for this edit. When
the song says "all I need is a beauty and a beat", the frame has to be the two of
them; a scorer that likes movement will hand you Spider-Man swinging.

So direction is a separate stage that produces SEGMENTS — (time range, shot,
act) — and the planner turns segments into cuts. Two rules, and they resolve
every disagreement between music and lyric:

  * the picture cuts on the beat, UNLESS a word is landing — then the word wins
    and the cut sits on the syllable;
  * the lyric decides WHICH shot, at the granularity of one line. When the line
    is long and rhythmic the moment is subdivided on 8ths, so the edit still
    moves; the shots it subdivides between come from the line's own shot pool.

Every pool here was chosen by watching the pack, not by a face count. The face
census said shots 31, 32 and 35 held one face; they are the embrace, the kiss and
an extreme close on both of them. A census measures how many faces it can find at
640x360 in one sampled frame, which is not the same question as "who is in this
shot".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .lyrics import lyric_cards


@dataclass
class Moment:
    """One line of the song, and the footage answering it."""
    at: float                 # output seconds, absolute on the edit timeline
    until: float
    shots: tuple[int, ...]    # pool, in preference order
    div: float = 1.0          # cuts per beat: 0.5 = a hold, 2 = 8ths
    act: str = "drop"
    src: float | None = None  # exact source in-point for the first cut
    ramp: str | None = None
    note: str = ""
    cuts: int | None = None   # exact number of cuts, overriding div

    @property
    def span(self) -> float:
        return self.until - self.at


# What is actually in each shot used above. Written by watching a stolen frame
# of every shot in the pack at once, because a face census said shots 31, 32 and
# 35 held ONE face and they are the embrace, the kiss and an extreme close on
# both of them. A detector counts faces it can resolve; it cannot tell you who
# the shot is about.
SHOT_NOTES = {
    0: "hallway, the two of them walking side by side",
    5: "classroom, she sits behind him",
    6: "over her shoulder at a table, close",
    7: "bright window, him at the sill",
    10: "subway car, the two of them",
    12: "hallway, both in frame, talking",
    13: "close on him, her head in the frame",
    14: "his face lit up at her — the brightest shot in the pack",
    15: "he hands her the ball — the ask",
    16: "lockers, she is at the edge of the frame",
    23: "classroom, warm, her in front of him",
    24: "him smiling, papers in hand",
    25: "him, flowers in the foreground",
    26: "table at her house, her head in the foreground",
    27: "the two of them facing each other, city at night",
    28: "rooftop, two figures, distance",
    29: "her alone in blue, night",
    30: "him alone, night",
    31: "the embrace on the rooftop",
    32: "the kiss on the rooftop",
    33: "Spider-Man crouched on a ledge, alone",
    34: "him, looking up, warm interior",
    35: "extreme close, both faces — the most intimate frame here",
}


# ---------------------------------------------------------------------------
# The opening. No vocal yet, so nothing has to be said; the job is to introduce
# the couple as a couple before the song asks for one. Every shot here has both
# of them in frame or her head in the foreground of his — the pack's warm,
# daylight half. Boundaries sit on bar/beat lines.
# ---------------------------------------------------------------------------
INTRO: list[Moment] = [
    Moment(0.00, 1.96, (0,), 0, "build", src=0.55, note="hallway, walking together"),
    Moment(1.96, 3.91, (12,), 0, "build", src=48.40, note="both in frame, talking"),
    Moment(3.91, 5.87, (6,), 0, "build", src=25.10, note="over her shoulder, close"),
    Moment(5.87, 7.34, (5,), 0, "build", src=21.60, note="class, she sits behind him"),
    Moment(7.34, 8.81, (16,), 0, "build", src=63.30, note="lockers, she is at the edge"),
    Moment(8.81, 10.28, (15,), 0, "build", src=59.40, note="he hands her the ball — the ask"),
    Moment(10.28, 11.26, (23,), 0, "build", src=104.60, note="classroom, warm"),
    Moment(11.26, 12.57, (13,), 0, "build", src=52.60, note="close on him, her head in frame"),
]

# ---------------------------------------------------------------------------
# The chorus. Keyed by card index from lyrics.lyric_cards, so the words on
# screen and the picture underneath can never drift apart: the same function
# that times the text decides when the shot changes.
#
#   card                        shot pool           why
#   0 All I need                35                  the closest frame in the pack
#   1 is a beauty               14                  his face lit up at her
#   2 and a beat (rhythmic)     31,27,35            motion on 8ths
#   3 Who can make (rhythmic)   27,31,32            the two of them, night
#   4 my life complete          32 (hold)           the kiss, one cut, no cutting
#   5 It's all yours           26,10,6             devotion: her, him, them
#   6 when I'm                  31,32               the flashback
#   7 not around                28,30,29            distance, him alone
#   8 It's all yours            33                  the cost, alone on a ledge
#   9 it's all yours            35                  back to her face
# ---------------------------------------------------------------------------
CARD_DIRECTION: dict[int, dict] = {
    0: dict(shots=(35,), div=1.0, src=150.60, note="extreme close, both faces"),
    1: dict(shots=(14,), div=1.0, src=55.60, note="his face, lit up"),
    2: dict(shots=(31, 27, 35), div=2.0, note="embrace, city, close — on 8ths"),
    3: dict(shots=(27, 31, 32), div=2.0, note="night, the two of them"),
    4: dict(shots=(32,), cuts=1, src=135.10, ramp="settle",
             note="the kiss: one cut, let it breathe"),
    5: dict(shots=(26, 10, 6), div=1.0, note="devotion"),
    6: dict(shots=(31, 32), div=1.0, note="flashback to the embrace and the kiss"),
    7: dict(shots=(28, 30, 29), div=1.0, note="distance, him alone"),
    8: dict(shots=(33,), div=1.0, note="alone on the ledge"),
    9: dict(shots=(35,), cuts=1, src=152.30, note="back to her face"),
}

# The one cut that is not on a lyric: the bar of instrumental after "complete",
# where the edit exhales and returns to daylight before the second half.
BRIDGE = (24, 25, 7, 23)
BRIDGE_DIV = 0.5


def moments_for(track: str, start: float, duration: float,
                bpm: float) -> list[Moment]:
    """Build the full directed timeline for the track window."""
    cards = lyric_cards(track, start, duration)
    if len(cards) < len(CARD_DIRECTION):
        raise RuntimeError(
            f"got {len(cards)} lyric cards, direction covers "
            f"{len(CARD_DIRECTION)} — the words on screen and the shot plan "
            f"have drifted apart")

    out = [m.__class__(**{**m.__dict__}) for m in INTRO]

    # instrumental bar: runs from the end of card 4 to the start of card 5
    gap_a, gap_b = cards[4]["end"], cards[5]["start"]
    if gap_b - gap_a > 0.5:
        n = max(2, round((gap_b - gap_a) * bpm / 60.0 * BRIDGE_DIV))
        step = (gap_b - gap_a) / n
        for i in range(n):
            out.append(Moment(gap_a + i * step, gap_a + (i + 1) * step,
                              (BRIDGE[i % len(BRIDGE)],), BRIDGE_DIV, "drop",
                              note="instrumental — back to daylight"))

    for i, card in enumerate(cards):
        d = CARD_DIRECTION.get(i)
        if d is None:
            continue
        out.append(Moment(card["start"], card["end"], tuple(d["shots"]),
                          d.get("div", 1.0), "drop", src=d.get("src"),
                          ramp=d.get("ramp"), note=d.get("note", ""),
                          cuts=d.get("cuts")))

    # the tail: after the last word, one slow frame, mono. The exhale.
    end = duration
    if end - cards[-1]["end"] > 0.4:
        out.append(Moment(cards[-1]["end"], end, (34,), 1.0, "out",
                          src=143.40, note="the exhale", cuts=1))
    out.sort(key=lambda m: m.at)
    return out


def segments_for(grid, source, track: str, start: float, duration: float):
    """Moments -> concrete segments the planner can turn into cuts.

    A moment's span is divided into `div` cuts per beat; each cut takes the next
    shot from the pool that is long enough to feed it. Source in-points come from
    the moment when it names one, otherwise from the planner's own in-point rule.
    """
    flat = []
    for m in moments_for(track, start, duration, grid.bpm):
        beats = (m.cuts if m.cuts
                 else max(1, round(m.span * grid.bpm / 60.0 * m.div)))
        step = m.span / beats
        n = len(m.shots)
        for k in range(beats):
            # rotate the pool so a subdivided moment actually alternates shots
            # instead of holding one frame in four identical pieces
            rot = k % n
            pool = list(m.shots[rot:]) + list(m.shots[:rot])
            flat.append({
                "start": m.at + k * step,
                "end": m.at + (k + 1) * step,
                "act": m.act,
                "pool": pool,
                "src": m.src if k == 0 else None,
                "ramp": m.ramp if k == 0 else None,
                "note": m.note,
            })
    return flat


def script_cards(track: str, start: float, duration: float, bpm: float,
                 pin: tuple[str, ...] = ("is a beauty", "my life complete",
                                         "not around")) -> list[dict]:
    """The on-screen words, straight from the aligned lyric.

    `beat` is beats from frame one, which is the contract `compose.card_time`
    implements. No word here is typed by hand, so no card can say something the
    song does not say.
    """
    cards = []
    for c in lyric_cards(track, start, duration):
        cards.append({
            "beat": round(c["start"] * bpm / 60.0, 3),
            "text": c["text"],
            "accent": c["accent"].upper() if c["accent"] else "",
            "pin": c["text"] in pin,
            # No matte on a lyric. The matte fills the letterforms with the plate
            # underneath, which is a great move on a lens close-up and a disaster
            # on a night rooftop: the word becomes the same tone as the sky and
            # the line the song is carrying disappears exactly when it matters.
            # Legibility is not negotiable on the words.
            "matte": False,
            "until": round(c["end"] * bpm / 60.0, 3),
        })
    return cards


def write(track: str, start: float, duration: float, bpm: float,
          script_path: str | Path, plan_path: str | Path | None = None) -> dict:
    cards = script_cards(track, start, duration, bpm)
    p = Path(script_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"cards": cards}, indent=1) + "\n")
    if plan_path:
        Path(plan_path).write_text(
            json.dumps([m.__dict__ for m in
                        moments_for(track, start, duration, bpm)], indent=1) + "\n")
    return {"cards": len(cards)}
