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
    4: dict(shots=(102, 103, 104, 105), div=0.8, note="AMAR MORAR again — the wound, further in"),
    5: dict(shots=(106, 107, 108, 109), div=0.8, note="KARON TUMII again — the dark, later"),
    6: dict(shots=(110, 92, 93, 94), div=0.8, note="ABAR BECHE again — what is left, later"),
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
    8: dict(shots=(43, 44, 47), div=1.0, note="mein karta hai — both of them"),
    9: dict(shots=(80, 81, 86), div=1.0, note="meri ruswaai — the closest they got"),
    10: dict(shots=(87, 88, 89), div=1.0, note="Tera kusoor — tenderness"),
    11: dict(shots=(90, 91, 100), div=1.2, ramp="settle", note="zaalima main kehlayi — hold"),
    12: dict(shots=(23, 24, 25), div=1.0, note="Deedaar tera — the hook again"),
    13: dict(shots=(26, 27, 28), div=1.0, note="ke baad hi — balcony"),
    14: dict(shots=(101, 84, 85), div=1.4, ramp="settle", note="angdaai — the last word"),
}

def pack_direction(source, n_lines: int, per_line: int = 4) -> dict:
    """A per-line shot pool built from the PACK, for a lyric we have no table for.

    `LINE_DIRECTION` and its siblings are hand-written: each line of one
    particular lyric mapped to shot indices that were chosen by watching one
    particular pack. Handing that table a different video is what produced the
    worst defect in the Ghost cut — lines with no entry inherited the previous
    line's pool (`direction.get(line, last_dir)`), every gap was filled from
    `FILL = (31, 27, 26, 35)`, and the table never names a shot above 35. On a
    451-second pack that meant the edit drew on 17 of 100 shots, never touched
    the last four and a half minutes, and repeated four shots for fifty seconds.

    So: divide the pack into one band of shots per line, in source order, and
    give each line its own band. The edit then walks the whole video from the
    first bar to the last, which is also how a montage cut to a song behaves —
    early lines look like the beginning, the last line looks like the end.

    Bands are ordered by source time and the longest shots in a band are
    preferred, because a line usually needs to hold.
    """
    shots = sorted(source.shots, key=lambda sh: sh.src_in)
    n = len(shots)
    if n == 0:
        return {}
    out: dict = {}
    for line in range(n_lines):
        lo = int(round(line * n / n_lines))
        hi = int(round((line + 1) * n / n_lines))
        band = shots[lo:hi] or shots[max(0, lo - 1):lo + 1] or shots
        # longest first, but keep the source order stable inside a band
        picks = sorted(band, key=lambda sh: -sh.dur)[:per_line]
        pool = tuple(sh.index for sh in sorted(picks, key=lambda sh: sh.src_in))
        out[line] = dict(shots=pool, div=1.0,
                         note=f"pack band {line + 1}/{n_lines}")
    return out


def pack_fill(source, n: int = 6) -> tuple[int, ...]:
    """A bridge pool from the whole pack, not four shots of one scene."""
    shots = sorted(source.shots, key=lambda sh: sh.src_in)
    if not shots:
        return FILL
    step = max(1, len(shots) // n)
    return tuple(shots[i].index for i in range(0, len(shots), step))[:n] or FILL


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



# The two post-2 edits are the same pack cut two ways, so they cannot open on
# the same images. The grief edit gets its own build: the silhouette, then him,
# then her, then the drop.
INTRO_BANGLA: list[Moment] = [
    Moment(0.00, 1.60, (40,), 0, "build", src=95.60, note="her face — the first thing you see"),
    Moment(1.60, 3.20, (56,), 0, "build", src=139.40, note="him, in the dark"),
    Moment(3.20, 4.80, (40,), 0, "build", src=95.60, note="her face, close"),
    Moment(4.80, 6.40, (60,), 0, "build", src=152.80, note="she looks up — the last good moment"),
    Moment(6.40, 8.00, (52,), 0, "build", src=130.60, note="the wound"),
    Moment(8.00, 9.60, (45,), 0, "build", src=117.10, note="headlights, rain — with light in it"),
    Moment(9.60, 11.20, (41,), 0, "build", src=99.80, note="her, again"),
    Moment(11.20, 12.80, (39,), 0, "build", src=88.90, note="the last look before the word"),
]

# The hook stops at 2:02 and the operator asked for the tape to 2:20. Eighteen
# seconds of music with no words is not dead air — it is the part of the edit
# the audience watches twice, so it gets its own images instead of the four
# shots that bridge an instrumental gap.
TAIL_BANGLA: tuple[int, ...] = (64, 66, 68, 70, 72, 74, 76, 78, 92, 94, 96, 98, 102, 104, 106, 108)

def _single_intro(first: float, start: float) -> list[Moment]:
    """The crescendo's opening: ONE image, held, no cuts at all.

    Deliberately not a montage. The whole promise of the format is that nothing
    has moved yet when the first word lands, so the cut into it is the event.
    """
    lead = first - start
    if lead <= 0.12:
        return []
    return [] if False else [Moment(start, first, (40,), 1.0, "build",
                                   src=95.60, cuts=1,
                                   note="held — nothing moves until the word")]


def _intro_for(first: float, start: float,
               template: list[Moment] | None = None) -> list[Moment]:
    """The build, sized to the air that actually exists before the first word.

    INTRO is written for a long instrumental. This track's first word lands about
    two and a half seconds after the edit starts, so the template has to be CUT
    DOWN — taking the tail of it, which is the part that accelerates into the
    drop — instead of the last cut being stretched to thirteen seconds, which is
    what happened and reads as a freeze.
    """
    INTRO = template or globals()["INTRO"]
    INTRO_TOTAL = sum(m.span for m in INTRO)
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


def _beats(cut_beats: int, at: float, until: float, shots: tuple[int, ...],
           div: float, act: str, note: str) -> list[Moment]:
    """One card -> its cuts, stepping through its shots in order.

    `cut_beats` is how many picture changes the card carries: 1 for a hold, 2 for
    a pair, 3 for a burst. Stepping rather than rotating means two beats never
    land on the same frame, which is what made a two-beat card read as a freeze.
    """
    n = len(shots)
    out = []
    for k in range(max(1, cut_beats)):
        out.append(Moment(at, until, (shots[k % n],), div, act,
                          note=f"{note} [{k + 1}/{cut_beats}]"))
    return out


def moments_from_words(cards: list[dict], bpm: float, duration: float,
                       start: float = 0.0, direction: dict | None = None,
                       word_mode: str = "pair", word_pool: tuple[int, ...] = (),
                       intro: list[Moment] | None = None,
                       tail_pool: tuple[int, ...] | None = None) -> list[Moment]:
    """Cut on the WORD, not on the card.

    The cards know where each word is. Cutting the picture on the card boundary
    alone means a three-word card is one image for a second and a half; cutting
    inside it means the shot changes under the word, which is the difference
    between "edited" and "choreographed". The cadence is chosen by the format:

        pair   — cut every two words (default; matches how the type changes)
        burst  — cut every word, capped so a fast line does not become a strobe
        hold   — never cut inside a card: the lyric carries it

    Cards keep their own shots for the first cut of each card; the extra cuts come
    from `word_pool`, which is the format's own set of images.
    """
    if not cards:
        raise ValueError("no caption cards — nothing to cut to")
    if intro == "single":
        out: list[Moment] = _single_intro(cards[0]["start"], start)
    else:
        out = _intro_for(cards[0]["start"], start, intro)
    prev_end = cards[0]["start"]
    direction = direction or LINE_DIRECTION
    last_dir = direction[max(direction)]
    pool = tail_pool or FILL
    n_pool = len(word_pool) or len(pool)
    k_pool = 0

    def fill(a: float, b: float, why: str):
        n = max(1, round((b - a) / FILL_HOLD))
        step = (b - a) / n
        for k in range(n):
            out.append(Moment(a + k * step, a + (k + 1) * step,
                              (pool[k % len(pool)],), 1.0, "drop", note=why))

    for i, card in enumerate(cards):
        gap = card["start"] - prev_end
        if gap > 0.005:
            if gap <= 0.35 and out:
                out[-1].until = card["start"]
            else:
                fill(prev_end, card["start"], "instrumental")
        d = direction.get(card["line"], last_dir)
        shots = list(d["shots"])
        span = card["end"] - card["start"]
        words = len(card["text"].split())
        if word_mode == "burst":
            cuts = max(1, min(words, 4))
        elif word_mode == "hold":
            cuts = 1
        else:
            cuts = max(1, min(2, words // 2 + words % 2))
        cuts = min(cuts, max(1, int(span / 0.34)))
        step = span / cuts
        for k in range(cuts):
            pooled = word_pool and (k > 0 or i % 2 == 1)
            shot = (word_pool[k_pool % n_pool] if pooled else shots[k % len(shots)])
            if pooled:
                k_pool += 1
            out.append(Moment(card["start"] + k * step,
                              card["start"] + (k + 1) * step,
                              (shot,), d.get("div", 1.0), "drop",
                              ramp=d.get("ramp") if k == cuts - 1 else None,
                              note=f"{d.get('note', 'line')} "
                                   f"[{k + 1}/{cuts}]"))
        prev_end = card["end"]

    # tail
    if duration > prev_end + 0.2:
        fill(prev_end, duration - 2.0 if duration - prev_end > 3.0 else duration,
             "tail — bridge to the end")
    if duration - prev_end > 3.0:
        out.append(Moment(duration - 2.0, duration, (58,), 1.0, "out",
                          src=149.20, cuts=1, note="the exhale"))
    out.sort(key=lambda m: m.at)
    return out


def moments_for(cards: list[dict], bpm: float, duration: float,
                start: float = 0.0, direction: dict | None = None,
                intro: list[Moment] | None = None,
                tail_pool: tuple[int, ...] | None = None) -> list[Moment]:
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
    out: list[Moment] = _intro_for(first, start, intro)

    direction = direction or LINE_DIRECTION
    last_dir = direction[max(direction)]
    line_first: dict[int, bool] = {}
    prev_end = first

    pool = tail_pool or FILL

    def fill(a: float, b: float, why: str):
        n = max(1, round((b - a) / FILL_HOLD))
        step = (b - a) / n
        for k in range(n):
            out.append(Moment(a + k * step, a + (k + 1) * step,
                              (pool[k % len(pool)],), 1.0, "drop",
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
                 start: float = 0.0, direction: dict | None = None,
                 intro: list[Moment] | None = None,
                 tail_pool: tuple[int, ...] | None = None,
                 behaviour: str | None = None,
                 word_pool: tuple[int, ...] | None = None,
                 max_cuts: int | None = None):
    """Moments -> concrete segments the planner can turn into cuts."""
    flat = []
    beh = BEHAVIOURS.get(behaviour or "lyric", BEHAVIOURS["lyric"])
    if behaviour and behaviour != "lyric":
        moments = moments_from_words(
            cards, grid.bpm, duration, start, direction,
            word_mode=beh.get("word_mode", "pair"),
            word_pool=word_pool or FILL, intro=intro or beh.get("intro"),
            tail_pool=tail_pool)
    else:
        moments = moments_for(cards, grid.bpm, duration, start, direction,
                              intro, tail_pool)
    word_cut = bool(behaviour and behaviour != "lyric")
    for m in moments:
        # A word-cut moment is already exactly one cut: re-subdividing it on the
        # grid is how a per-word edit turned into four cuts per word and read as
        # a strobe.
        beats = 1 if word_cut else (m.cuts if m.cuts
                 else max(1, min(4, round(m.span * grid.bpm / 60.0 * m.div))))
        # A format can cap the subdivision. Reference 2 holds a shot for two to
        # four seconds and lets the type carry the rhythm, so its moments are
        # one cut each; the default grid subdivision is what turns that into a
        # metronome.
        if max_cuts:
            beats = max(1, min(beats, max_cuts))
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

# ---------------------------------------------------------------------------
# Behaviours — one format, one way of cutting. These are house rules, not shot
# lists: they say WHAT KIND of image goes where, and the direction map still
# says which film moment. Rotating these is how two edits off one pack stop
# looking like the same video.
#
#   lyric     — default. One image per card, held; the type leads.
#   crescendo — nothing cuts until the first card, then one cut per word. The
#               stillness is the idea: 90% of edits are cut-cut-cut from frame
#               one, so holding still is the thing that reads as confident.
#   mosaic    — one word per card, a new image every word, no hold anywhere.
#               Busy on purpose; the only format that can carry a fast song.
# ---------------------------------------------------------------------------
BEHAVIOURS: dict[str, dict] = {
    "lyric": {"word_mode": "pair", "intro": None, "fill_hold": 0.55},
    "crescendo": {"word_mode": "burst", "intro": "single",
                  "fill_hold": 0.85, "static_intro": True},
    "mosaic": {"word_mode": "burst", "intro": None, "fill_hold": 0.34},
}

INTROS = {"post2_bangla": INTRO_BANGLA}

# The extra images a word-cut needs, beyond the ones each card already names.
# Kept inside the brief's own half of the pack: a burst cut that borrows from
# another edit's shots is how two videos off one pack start to look alike.
WORD_POOLS = {
    "post2_zaalima": (7, 24, 27, 37, 46, 81, 86, 89),
}

TAILS = {"post2_bangla": TAIL_BANGLA}
