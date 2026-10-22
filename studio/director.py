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
#   line                                     pool                 why
#   ----------------------------------------------------------------  -------
#   0 We young tonight                     27,31,28   night, the two of them
#   1 I'm coming for ya                     10,0,12,23  he comes to her
#   2 'Cause all I need                    35,14      the closest frames
#   3 Is a beauty and a beat                29,6,26    her
#   4 Who can make my life complete         32,31      the kiss
#   5 It's all all 'bout you                26,35,31   devotion
#   6 When the music makes you move         31,27,32   motion inside the moment
#   7 Baby, do it like you do               35,32,31   back to her face
#
# This lyric is the chorus of "Beauty and a Beat", eight lines, repeated words.
# The pool for a line is the pair, never one of them alone: the brief is the
# couple, and the pack's warm daylight singles (24, 25, 30, 34) belong to the
# opening and to nothing else. Rhythm comes from `div` — 2 cuts per beat turns a
# long card into eighths — never from cutting to a shot the line is not about.
LINE_DIRECTION: dict[int, dict] = {
    0: dict(shots=(27, 31, 28, 35), div=1.0, note="night, the two of them"),
    1: dict(shots=(10, 0, 12, 16, 15, 23), div=2.0, note="the approach"),
    2: dict(shots=(35, 14, 26, 31), div=1.0, note="the closest frames"),
    3: dict(shots=(29, 6, 26, 32), div=1.0, note="her"),
    4: dict(shots=(31, 27, 32, 35), div=1.0, note="the embrace, the city, the kiss"),
    5: dict(shots=(26, 10, 0, 16, 31), div=2.0, note="devotion"),
    6: dict(shots=(27, 31, 32, 12, 23), div=2.0, note="motion inside the moment"),
    7: dict(shots=(35, 32, 29, 31, 6), div=2.0, note="back to her face"),
}

# ---------------------------------------------------------------------------
# Tom Holland — Spider-Man: Brand New Day, cut to "Stay".
#
# The pack is Peter and the suit; there is no MJ in it (checked frame by frame),
# so the couple line is played on Peter alone. That changes the read from "the
# two of them" to "the one who stayed" — and it is the honest reading of the
# footage rather than a guess at what the lyric wanted.
#
#   #00-03   shop, Peter in the street, wide
#   #13-14   Peter close, the DELI tee, the face
#   #15-25   suit in a doorway, crouched, the rain, the fight
#   #26-32   Peter in the green jacket, in the crowd, walking
#   #31,43,53-63  the swings: the pack's whole point
#   #34-35   the pool, desaturated and strange — used once, as a breath
#
# "Stay" is 143 BPM pop-punk: the chorus wants eighths (div 2.0) but a whole
# edit at div 2.0 is 0.23s cuts, which is a strobe, not an overedit. The build is
# div 1.0 on singles, the choruses are div 1.5, and the last line is one hold.
LINE_DIRECTION_TOM: dict[int, dict] = {
    # One entry per SUNG LINE, in the order the edit actually hears them. This
    # map was written for a 14-line reading of the song; the edit resolves to 12
    # (the last chorus sings "I need you to stay" twice), so the keys were one
    # to three lines out of step with the cards on screen — the direction was
    # following the lyric sheet, not the vocal.
    #
    # Pools are six deep, each shot checked against work/studio/th_all_shots.jpg.
    # A sung line earns five or six cuts, so a three-shot pool has to bring a
    # shot back inside a second and the pack reads as a loop.
    0: dict(shots=(14, 27, 13, 18, 19, 51), div=1.0,
            note="'right here' — him, close"),
    1: dict(shots=(31, 32, 26, 30, 40, 41), div=1.0, note="between the two"),
    2: dict(shots=(18, 19, 51, 27, 13, 50), div=1.0, note="the face, the cost"),
    3: dict(shots=(31, 43, 53, 54, 44, 63), div=1.0, note="the swing, opening"),
    4: dict(shots=(59, 60, 62, 22, 21, 57), div=1.0, note="mid-swing, the crouch"),
    5: dict(shots=(45, 44, 28, 29, 46, 25), div=1.0, note="the climb, the crowd"),
    6: dict(shots=(56, 55, 48, 49, 47, 52), div=1.0, note="the rooftop, the city"),
    7: dict(shots=(53, 54, 61, 63, 43, 62), div=1.0, note="second chorus, bigger"),
    8: dict(shots=(60, 62, 22, 23, 20, 24), div=1.0, note="the fight"),
    9: dict(shots=(61, 63, 57, 24, 23, 25), div=1.0,
            note="the last 'stay' — the fight, wider"),
    10: dict(shots=(58, 27, 14, 31, 26, 51), div=1.0,
             note="'miss your touch' — the hands, then him, alone"),
    11: dict(shots=(58,), cuts=1, ramp="settle",
             note="'believe in love' — one hold, the hands"),
}

# ---------------------------------------------------------------------------
# Post 2 — the same pack, two songs. The Amazing Spider-Man scenepack is 111
# shots in two halves: #0-62 plain, #63-111 the same material Twixtor'd. Both
# directions work the plain half and take Twixtor frames where a hold needs
# slow motion. The two title cards (#0, #63) are burned-in text, never used.
#
# The split is the point: one edit is the grief, the other is the tenderness.
# They should not share a frame, so the packs are disjoint on purpose.
# ---------------------------------------------------------------------------
LINE_DIRECTION_BANGLA: dict[int, dict] = {
    # Faahun — metal, four sung phrases of two cards each, 1.5-2.3s a card.
    # The grief half of the pack: her face at the wound, him in the dark after.
    0: dict(shots=(42, 41, 43, 40), div=0.8, note="AMAR MORAR — her, already crying"),
    1: dict(shots=(52, 53, 55, 54), div=0.8, note="KARON TUMII — the dark behind her"),
    2: dict(shots=(56, 57, 50, 51), div=0.8, note="ABAR BECHE — what is left of him"),
    3: dict(shots=(96, 97, 98, 99), div=0.8, note="THAKAR DAYII — the reason he stayed"),
    4: dict(shots=(40, 42, 41, 43), div=0.8, note="AMAR MORAR again — the same wound"),
    5: dict(shots=(53, 54, 52, 55), div=0.8, note="KARON TUMII again"),
    6: dict(shots=(104, 105, 106, 103), div=0.8, note="ABAR BECHE again"),
    7: dict(shots=(58, 59, 60, 61), div=1.6, ramp="settle", note="DAYII — hold on the last word"),
}

LINE_DIRECTION_ZAALIMA: dict[int, dict] = {
    # Zaalima — the warm half: the lab, the rooftop, the two-shots. Nothing from
    # the fall, nothing from the dark, so the two edits share no frame.
    0: dict(shots=(4, 5, 6), div=1.0, note="Deedaar tera — after seeing you"),
    1: dict(shots=(8, 10, 11), div=1.0, note="milne ke baad — the first look"),
    2: dict(shots=(9, 29, 30), div=1.0, note="chhute meri angdaai — her laugh"),
    3: dict(shots=(12, 13, 14), div=1.0, note="Tu hi bata — mid-argument"),
    4: dict(shots=(15, 16, 17), div=1.0, note="de kyun zaalima — the world watching"),
    5: dict(shots=(18, 19, 20), div=1.0, note="main kehlayi — the blame lands on her"),
    6: dict(shots=(34, 35, 36), div=1.0, note="Kyun is tarah — the rooftop"),
    7: dict(shots=(37, 38, 39), div=1.0, note="se duniya jahan — city below"),
    8: dict(shots=(44, 45, 46), div=1.0, note="mein karta hai — both of them"),
    9: dict(shots=(80, 81, 86), div=1.0, note="meri ruswaai — the closest they got"),
    10: dict(shots=(87, 88, 89), div=1.0, note="Tera kusoor — tenderness"),
    11: dict(shots=(90, 91, 100), div=1.2, ramp="settle", note="zaalima main kehlayi — hold"),
    12: dict(shots=(23, 24, 25), div=1.0, note="Deedaar tera — the hook again"),
    13: dict(shots=(26, 27, 28), div=1.0, note="ke baad hi — balcony"),
    14: dict(shots=(101, 84, 85), div=1.4, ramp="settle", note="angdaai — the last word"),
}

DIRECTIONS = {"peter_gwen": LINE_DIRECTION,
              "tom_holland_bnd": LINE_DIRECTION_TOM,
              "post2_bangla": LINE_DIRECTION_BANGLA,
              "post2_zaalima": LINE_DIRECTION_ZAALIMA}

# The bar of instrumental between "I need" and its answer, where the edit
# breathes. Still the couple: a bridge is a change of pace, not of subject.
BRIDGE = (31, 27, 26)
BRIDGE_DIV = 0.5


FILL = (31, 27, 26, 35)     # the couple, used to bridge an instrumental gap
FILL_HOLD = 0.55            # seconds per cut in a bridge


INTRO_TOTAL = sum(m.span for m in INTRO)


def _intro_for(first: float, start: float) -> list[Moment]:
    """The build, sized to the air that actually exists before the first word.

    INTRO is written for a long instrumental. This track's first word lands about
    two and a half seconds after the edit starts, so the template has to be CUT
    DOWN — taking the tail of it, which is the part that accelerates into the
    drop — instead of the last cut being stretched to thirteen seconds, which is
    what happened and reads as a freeze.
    """
    lead = first - start
    if lead <= 0.12:
        return []
    if lead >= INTRO_TOTAL:
        out = [m.__class__(**{**m.__dict__}) for m in INTRO]
        shift = first - out[-1].until          # land the last beat on the word
        for m in out:
            m.at += shift
            m.until += shift
        return out
    picked: list[Moment] = []
    total = 0.0
    for m in reversed(INTRO):
        picked.insert(0, m.__class__(**{**m.__dict__}))
        total += m.span
        if total >= lead:
            break
    k = lead / total
    t = start
    for m in picked:
        d = m.span * k
        m.at, m.until = t, t + d
        t += d
    return picked


def moments_for(cards: list[dict], bpm: float, duration: float,
                start: float = 0.0, direction: dict | None = None) -> list[Moment]:
    """Cards + sung lines -> a directed timeline with NO holes in it.

    One cut per card, because the picture should change when the word does. Two
    things the earlier version got wrong:

      * it built one moment per LINE, so a line whose cards were spread across an
        instrumental became a single 7-second cut;
      * it left the instrumental between lines unplanned, which leaves holes in
        the timeline — the encoder then runs picture and sound out of step.

    Every gap is now filled explicitly, so the plan is contiguous by construction.
    """
    if not cards:
        raise ValueError("no caption cards — nothing to cut to")

    first = cards[0]["start"]
    out: list[Moment] = _intro_for(first, start)

    direction = direction or LINE_DIRECTION
    last_dir = direction[max(direction)]
    line_first: dict[int, bool] = {}
    prev_end = first

    def fill(a: float, b: float, why: str):
        n = max(1, round((b - a) / FILL_HOLD))
        step = (b - a) / n
        for k in range(n):
            out.append(Moment(a + k * step, a + (k + 1) * step,
                              (FILL[k % len(FILL)],), 1.0, "drop",
                              note=why))

    # cards of one sung line, in order — the unit a direction is written for
    groups: list[list[dict]] = []
    for c in cards:
        if groups and groups[-1][0]["line"] == c["line"]:
            groups[-1].append(c)
        else:
            groups.append([c])

    for group in groups:
        line = group[0]["line"]
        d = direction.get(line, last_dir)
        fresh = not line_first.get(line, False)
        line_first[line] = True

        def lead_in(at: float) -> None:
            nonlocal prev_end
            gap = at - prev_end
            if gap > 0.005:
                if gap <= 0.35 and out:
                    # a card can end on its word and leave a few frames before
                    # the next one starts. Do not invent a cut for 60ms of
                    # silence — hold the previous shot through it.
                    out[-1].until = at
                else:
                    fill(prev_end, at, "instrumental — back to daylight")

        # A line marked `cuts` is ONE image however many cards it carries.
        # "You're the reason I believe in love" is four cards and one exhale;
        # treating each card as its own moment cut four times inside the hold
        # and turned the last two seconds into four dark frames in a row.
        if d.get("cuts") is not None and len(group) > 1:
            at, until = group[0]["start"], group[-1]["end"]
            lead_in(at)
            out.append(Moment(at, until, tuple(d["shots"]), d.get("div", 1.0),
                              "drop", src=d.get("src"), ramp=d.get("ramp"),
                              note=d.get("note", ""), cuts=d.get("cuts")))
            prev_end = until
            continue

        for c in group:
            lead_in(c["start"])
            # `div` is what makes a long card overedit instead of holding: the
            # card's own duration decides how many cuts it earns.
            out.append(Moment(c["start"], c["end"], tuple(d["shots"]),
                              d.get("div", 1.0), "drop",
                              src=d.get("src") if fresh else None,
                              ramp=d.get("ramp") if fresh else None,
                              note=d.get("note", ""), cuts=d.get("cuts")))
            prev_end = c["end"]
            fresh = False

    gap = duration - prev_end
    if gap > 0.25:
        # A tail is a breath, not a twelfth shot. Anything longer than a couple
        # of seconds gets bridge cuts and THEN a short exhale, because a single
        # 26-second hold at quarter speed is not slow motion, it is a stuck file.
        exhale = min(2.0, gap)
        if gap - exhale > 0.6:
            fill(prev_end, duration - exhale, "tail — bridge to the end")
        # One hold, not a sub-divided one: cutting inside a 0.55x settle means
        # the source jumps backwards under a slow image, which reads as a
        # stutter. The exhalation is a single, uncut breath.
        out.append(Moment(duration - exhale, duration, (34,), 1.0, "out",
                          src=143.40, note="the exhale", cuts=1))
    out.sort(key=lambda m: m.at)
    return out


def segments_for(grid, source, cards: list[dict], duration: float,
                 start: float = 0.0, direction: dict | None = None):
    """Moments -> concrete segments the planner can turn into cuts."""
    flat = []
    for m in moments_for(cards, grid.bpm, duration, start, direction):
        beats = (m.cuts if m.cuts
                 else max(1, min(4, round(m.span * grid.bpm / 60.0 * m.div))))
        step = m.span / beats
        n = len(m.shots)
        for k in range(beats):
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


