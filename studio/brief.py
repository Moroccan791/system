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
    song: str = ""          # what the caption calls the track: "Stay — …"
    lang: str = "en"        # ISO code. Non-English changes how the edit is verified.
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
            "track": self.track, "song": self.song, "source": self.source,
            "lang": self.lang,
            "window": list(self.window),
            "audience": [{"claim": e.claim, "source": e.source}
                         for e in self.audience],
            "lyric": [{"line": li.line, "needs": li.needs, "why": li.why}
                      for li in self.lyric],
            "avoid": self.avoid,
            "tags": self.tags, "hooks": self.hooks,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StudioBrief":
        return cls(
            title=d.get("title", ""),
            topic=d.get("topic", ""),
            thesis=d.get("thesis", ""),
            audience=[Evidence(**e) for e in d.get("audience", [])],
            lyric=[LyricIntent(**li) for li in d.get("lyric", [])],
            avoid=list(d.get("avoid", [])),
            tags=list(d.get("tags", [])),
            hooks=list(d.get("hooks", [])),
            track=d.get("track", ""),
            song=d.get("song", ""),
            lang=d.get("lang", "en"),
            source=d.get("source", ""),
            window=tuple(d.get("window", (0.0, 0.0))) or (0.0, 0.0),
        )

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
    song="Beauty and a Beat (slowed)",
    source="footage/spiderman_scenepack.mp4",
    window=(27.75, 62.0),
)


# New briefs live in studio/briefs/<name>.json — one video a day means a brief a
# day, and a brief is data. The two that predate the folder are still here:
# peter_gwen below, and tom_holland_bnd in the folder with the rest.

BRIEFS = {"peter_gwen": PETER_GWEN}

# A video a day means a brief a day, and editing Python to add one is how a
# standing workflow stops being standing. A brief can also be a JSON file:
#
#     studio/briefs/<name>.json   {"title": ..., "hooks": [...], "tags": [...]}
#
# Written by research, read by the pipeline, never templated.
BRIEF_DIR = Path("studio/briefs")


def names() -> list[str]:
    """Every brief the pipeline can render for — code first, then files."""
    on_disk = ([p.stem for p in BRIEF_DIR.glob("*.json")]
               if BRIEF_DIR.exists() else [])
    return sorted(set(BRIEFS) | set(on_disk))


def load(name: str = "peter_gwen") -> StudioBrief:
    if name in BRIEFS:
        return BRIEFS[name]
    path = BRIEF_DIR / f"{name}.json"
    if path.exists():
        return StudioBrief.from_dict(json.loads(path.read_text()))
    raise KeyError(f"no brief {name!r} — known briefs: {', '.join(names())}")


def save(brief: StudioBrief, name: str) -> Path:
    """Write a researched brief where `load()` will find it."""
    p = BRIEF_DIR / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(brief.as_dict(), indent=1, ensure_ascii=False) + "\n")
    return p
