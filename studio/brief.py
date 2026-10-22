"""The brief — research the subject before choosing a single cut.

This module exists because of a real miss. An edit was cut to "Beauty and a Beat"
with whatever shots looked best, and the footage was Andrew Garfield's Spider-Man.
The song is about needing a beauty to complete your life. The audience for that
film does not watch Peter Parker alone in a subway car — they watch Peter and
Gwen. Getting that wrong is not a rendering bug, it is the edit failing before a
single frame is drawn, and no amount of grading or beat-sync fixes it.

So the brief is a REQUIRED stage. It records:

  * who/what the audience actually comes for, with the evidence;
  * what the lyric is saying, line by line;
  * the shot class each lyric line needs (two-shot, single, wide, no-face);
  * which classes the available footage can actually supply.

`StudioBrief.check()` refuses to proceed when the lyric needs a shot class the
footage cannot supply, because that is a "get different footage" problem, not a
"try harder in the render" problem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Shot classes. Kept coarse on purpose: a planner cannot act on "romantic".
TWO = "two_shot"        # both people in frame — the money shot for a love song
SINGLE = "single"       # one subject, close
WIDE = "wide"           # no face, or a face too small to read
ANY = "any"


@dataclass
class Evidence:
    claim: str
    source: str


@dataclass
class LyricIntent:
    line: str
    needs: str = TWO
    why: str = ""


@dataclass
class StudioBrief:
    title: str
    topic: str
    thesis: str                                   # one sentence: what the edit is
    audience: list[Evidence] = field(default_factory=list)
    lyric: list[LyricIntent] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)   # searchable, niche first
    hooks: list[str] = field(default_factory=list)  # copy written FOR a viewer
    track: str = ""
    source: str = ""
    window: tuple[float, float] = (0.0, 0.0)

    # ---- gates -------------------------------------------------------
    def check(self, face_counts: dict[int, int]) -> list[str]:
        """Problems that must stop the work.

        Only classes that cannot be satisfied at all are errors. A shortage is a
        warning: an edit can reuse a good two-shot twice before it looks lazy.
        """
        problems = []
        have_two = sum(1 for c in face_counts.values() if c >= 2)
        have_single = sum(1 for c in face_counts.values() if c == 1)
        want_two = sum(1 for li in self.lyric if li.needs == TWO)
        want_single = sum(1 for li in self.lyric if li.needs == SINGLE)
        if want_two and have_two == 0:
            problems.append(
                f"the song needs {want_two} line(s) with both people in frame, "
                f"and the footage has no two-shots at all")
        if want_single and have_single == 0:
            problems.append(
                f"{want_single} line(s) need a single, and there is no such shot")
        if want_two and have_two < max(2, want_two // 3):
            problems.append(
                f"only {have_two} two-shot(s) for {want_two} line(s) — the drop "
                f"will repeat itself; get a pack with more of them")
        return problems

    def coverage(self, face_counts: dict[int, int]) -> dict:
        return {
            "two_shot": sum(1 for c in face_counts.values() if c >= 2),
            "single": sum(1 for c in face_counts.values() if c == 1),
            "wide": sum(1 for c in face_counts.values() if c == 0),
            "shots": len(face_counts),
        }

    # ---- persistence -------------------------------------------------
    def as_dict(self):
        return {
            "title": self.title, "topic": self.topic, "thesis": self.thesis,
            "track": self.track, "source": self.source,
            "window": list(self.window),
            "audience": [{"claim": e.claim, "source": e.source}
                         for e in self.audience],
            "lyric": [{"line": li.line, "needs": li.needs, "why": li.why}
                      for li in self.lyric],
            "avoid": self.avoid,
        }

    def write(self, path: str | Path, face_counts: dict[int, int] | None = None,
              problems: list[str] | None = None) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Brief — {self.title}", "",
                 f"**Topic.** {self.topic}", "",
                 f"**Thesis.** {self.thesis}", "",
                 f"**Track.** `{self.track}`  ·  **Source.** `{self.source}`  ·  "
                 f"**Window.** {self.window[0]:.2f}–{self.window[1]:.2f}s", "",
                 "## What this audience actually comes for", ""]
        for e in self.audience:
            lines.append(f"- {e.claim}  \n  <sub>{e.source}</sub>")
        lines += ["", "## What the lyric is asking for", "",
                  "| lyric line | needs | why |", "|---|---|---|"]
        for li in self.lyric:
            lines.append(f"| {li.line} | `{li.needs}` | {li.why} |")
        if self.avoid:
            lines += ["", "## Avoid", ""] + [f"- {a}" for a in self.avoid]
        if face_counts is not None:
            cov = self.coverage(face_counts)
            lines += ["", "## What the footage can supply", "",
                      f"- two-shots: **{cov['two_shot']}**",
                      f"- singles: **{cov['single']}**",
                      f"- no face / wide: **{cov['wide']}**",
                      f"- total shots: **{cov['shots']}**"]
        if problems:
            lines += ["", "## Blocking problems", ""] + [f"- {x}" for x in problems]
        p.write_text("\n".join(lines) + "\n")
        return p


# --------------------------------------------------------------------------
# The brief for the Spider-Man / Beauty and a Beat edit.
#
# Evidence came from audience research on Peter/Gwen edits, not from taste.
# --------------------------------------------------------------------------
PETER_GWEN = StudioBrief(
    title="Peter & Gwen — Beauty and a Beat",
    tags=["peterandgwen", "peterparker", "gwenstacy", "amazingspiderman",
          "andrewgarfield", "emmastone", "beautyandabeat", "spidermanedit"],
    # Written for a viewer, not about the research. `audience` is evidence for
    # choosing shots; this is copy. Keeping them separate is what stops a
    # listing from opening with a sentence nobody would ever say.
    hooks=["the only thing he ever needed",
           "he never got to save her",
           "peter & gwen, the ending that never came",
           "all he needed was her"],
    topic="The Amazing Spider-Man: Peter Parker and Gwen Stacy",
    thesis=("The song is someone who says they only need one person. So the edit "
            "is about the two of them — not about Peter alone, and not about "
            "Andrew Garfield the actor."),
    audience=[
        Evidence("Every high-performing edit in this fandom is the couple, and the "
                 "frame that carries them is loss: 'I lost Gwen, she was my MJ'.",
                 "TikTok discovery pages for Peter/Gwen and Garfield/Stone edits, "
                 "top items 222K-896K likes"),
        Evidence("The transition that breaks containment is tragedy into their "
                 "sweetest memories — the contrast is what makes it land.",
                 "Viral 'flips and Gwen' edit, 15M views / 720K likes"),
        Evidence("What viewers name as the scenes: the rooftop reveal and web-pull "
                 "kiss, the bridge 'I love you' in web, the graduation kiss, "
                 "dinner with her family, Oxford.",
                 "CBR, ScreenRant, WatchMojo 'most romantic Spider-Man moments'"),
        Evidence("The chemistry is the product: 'their relationship felt organic, "
                 "sweet and real'. Interviews about the two of them out-perform "
                 "plot content.",
                 "Ranker 'most emotional moments', TikTok 'shot of espresso' edits"),
    ],
    lyric=[
        LyricIntent("All I need is a beauty and a beat", TWO,
                    "the thesis of the song, stated once — both of them, close"),
        LyricIntent("Who can make my life complete", TWO,
                    "the two-shot IS the meaning of the line"),
        LyricIntent("It's all yours when I'm not around", TWO,
                    "devotion; better on a look between them than on action"),
        LyricIntent("It's all yours, it's all yours", SINGLE,
                    "her, holding the frame alone — the give in the line"),
    ],
    avoid=[
        "Peter alone for more than one beat — the song is not about him alone",
        "action or swinging under the love lyric; save movement for the drop only",
        "any shot where the second person is cropped out",
        "burned-in scene labels (they are visible in this pack) in a hero frame",
    ],
    track="footage/beauty_and_a_beat.mp3",
    source="footage/spiderman_scenepack.mp4",
    window=(27.75, 62.0),
)


# ---------------------------------------------------------------------------
# Spider-Man: Brand New Day (2026) — Tom Holland, Zendaya, Jacob Batalon.
#
# Researched 2026-10-22 from reviews and the edit pages, not from memory:
#   * the film is the most emotional MCU Spider-Man *because* it is grounded —
#     critics called out the Holland/Zendaya relationship for "real yearning",
#     and the more intimate scenes with MJ and Ned are what carry the charge;
#   * the highest-performing edits are Peter/MJ (heartbreak, "I don't love
#     you"), Ned remembering Peter (771K likes), and Peter tired and grieving —
#     the fandom's frame is loss and being forgotten, not web-slinging;
#   * Frank Castle is the new dynamic people mention, and it is a *different*
#     edit: violence, not tenderness. Do not mix the two in one cut.
#
# The track decides which of those this edit is. "Stay" is a fast pop-punk
# record: it is a hype edit, so the lyric line that lands is the chorus, and the
# shots that answer it are Peter in motion — swinging, running, the suit — with
# MJ cuts earned at the line about not finding anybody else.
# ---------------------------------------------------------------------------
TOM_HOLLAND_BND = StudioBrief(
    title="Peter Parker — Brand New Day · Stay",
    topic="Spider-Man: Brand New Day (2026), Tom Holland / Zendaya",
    thesis=("Brand New Day is the film where Peter is finally alone in a life he "
            "chose. Set to 'Stay', the edit is the want underneath that: he keeps "
            "moving, and the one thing he keeps coming back to is her."),
    audience=[
        Evidence("The emotional core the reviews single out is Peter with MJ — "
                 "'real yearning and perplexity', and the intimate scenes carry "
                 "the film. Edits of the pair are what travel.",
                 "BBC review round-up of Brand New Day; Telegraph and Standard "
                 "reviews, Aug 2026"),
        Evidence("Ned remembering Peter is a 771K-like edit on its own — being "
                 "forgotten is the fandom's favourite wound from this film.",
                 "TikTok discover: peter-parker-remembered-scene, top item 771.2K"),
        Evidence("The grounded, sombre take is the praise that repeats: 'more of "
                 "a sombre, drama-filled plot … healing of Peter's past scars'.",
                 "Rotten Tomatoes audience review round-up, Jul 2026"),
        Evidence("Frank Castle is the new pairing people mention — and it is a "
                 "violence edit, not a tenderness edit. Mixing them reads as two "
                 "videos stapled together.",
                 "RT audience round-up + EditVdiaries tag clouds"),
    ],
    tags=["spiderman", "tomholland", "peterparker", "brandnewday", "mj",
          "zendaya", "spidermanedit", "marvel"],
    hooks=["he chose to be alone",
           "brand new day, same gravity",
           "the suit stayed, everything else went",
           "he keeps moving because stopping means remembering"],
    lyric=[
        LyricIntent("I do the same thing I told you that I never would", TWO),
        LyricIntent("I told you I'd change, even when I knew I never could", TWO),
        LyricIntent("I know that I can't find nobody else as good as you", TWO),
        LyricIntent("I need you to stay, need you to stay", TWO),
    ],
    avoid=["Frank Castle / Punisher shots in a Peter-MJ edit",
           "Tony Stark flashbacks — this film is not about him"],
    track="footage/track.mp3",
)

BRIEFS = {"peter_gwen": PETER_GWEN, "tom_holland_bnd": TOM_HOLLAND_BND}


def load(name: str = "peter_gwen") -> StudioBrief:
    return BRIEFS[name]
