"""The listing — title, description, hashtags — as a stage, not an afterthought.

An edit that is good and a listing that is generic is a video the algorithm
never shows anyone. The listing is written from the same brief the edit came
from: the audience row that decided the shots also decides the hook, because
both are answering "why does someone stop scrolling for this".

What this module will not do is pretend a template is taste. It writes a first
draft you can edit, in three variations, and it enforces the platform limits so
a good hook does not get truncated at 95 characters.

    python -m studio.publish --brief peter_gwen --track beauty_and_a_beat \\
        --duration 43 --out work/studio/spiderman.publish.md

Platform rules encoded (2026, checked against each platform's own limits):

| where | title/caption | hashtags |
|---|---|---|
| TikTok | 2200 chars, first ~55 visible before "more" | 3-5, from the niche |
| Instagram Reels | 2200, first 125 visible | 3-5, in the caption |
| YouTube Shorts | title 100, first 40 matter | 3 in the title, rest in the description |

A hashtag earns its place by being one a viewer would search, not by describing
the video in the abstract — "#edit" is noise, "#peterandgwen" is a search.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---- platform limits -------------------------------------------------------
LIMITS = {
    "tiktok": {"caption": 2200, "visible": 55, "tags": 5, "title": None},
    "reels": {"caption": 2200, "visible": 125, "tags": 5, "title": None},
    "shorts": {"caption": 5000, "visible": 100, "tags": 3, "title": 100},
}


@dataclass
class Listing:
    titles: list[str] = field(default_factory=list)
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    hook: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"hook": self.hook, "titles": self.titles,
                "description": self.description, "hashtags": self.hashtags,
                "notes": self.notes}


def _clip(text: str, n: int) -> str:
    """Cut to a word boundary at or under n characters. No mid-word ellipsis."""
    text = text.strip().rstrip(".")
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut


def tags_for(brief, extra: list[str] | None = None, limit: int = 5) -> list[str]:
    """Searchable tags, niche first. Broad tags ride on a niche that already works."""
    base, seen = [], set()
    for t in ([*(extra or []), *(getattr(brief, "tags", []) or [])]):
        t = t.strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            base.append(t.lower().replace(" ", ""))
    return base[:limit]


def write(brief, duration: float, titles: int = 3, track: str = "",
          extra_tags: list[str] | None = None) -> Listing:
    """Three hooks from the brief, one description, one tag set.

    The hook is the one sentence a viewer would repeat: a pairing, a loss, or a
    promise. It is written from `brief.thesis` (what the edit IS) and the
    audience evidence (what this fandom actually responds to), never from the
    render.
    """
    who = getattr(brief, "title", "the edit")
    thesis = getattr(brief, "thesis", "").strip().rstrip(".")
    aud = getattr(brief, "audience", []) or []
    hook_src = aud[0].claim if aud else ""
    tags = tags_for(brief, extra_tags, LIMITS["tiktok"]["tags"])

    # The hook is a clause a viewer could repeat, not a summary. Take the
    # strongest audience claim, clip it at a word boundary, and let the title
    # carry the names — a listing that opens with a sentence nobody says is a
    # listing nobody clicks.
    candidates = list(getattr(brief, "hooks", []) or [])
    if hook_src and not candidates:
        candidates.append(_clip(hook_src.split(":")[0], 62))
        candidates.append(_clip(hook_src, 62))
    if thesis and not candidates:
        candidates.append(_clip(thesis.split(",")[0].split("—")[0], 62))
    candidates.append(who)
    candidates.append(f"{who} · {duration:.0f}s")

    def sentence_case(c: str) -> str:
        # capitalise the opening and any name after an ampersand; never lower
        # anything, because "Gwen" is not "gwen".
        parts = c.split(" & ")
        parts = [x[:1].upper() + x[1:] if x else x for x in parts]
        return " & ".join(parts)

    titles_out = []
    for c in candidates:
        c = sentence_case(c)
        if c not in titles_out and len(c) <= LIMITS["shorts"]["title"]:
            titles_out.append(c)
    titles_out = titles_out[:titles]

    hook = titles_out[0] if titles_out else who
    desc_lines = [hook, ""]
    if track:
        desc_lines.append(f"♪ {track}")
    desc_lines.append("edited by hand, cut to the song")
    desc_lines.append("")
    desc_lines.append(" ".join("#" + t for t in tags))

    notes = []
    if not getattr(brief, "hooks", None):
        notes.append("this brief has no viewer-facing hooks — the title fell back to "
                     "the subject line. Write 3-4 in brief.hooks and the drafts improve.")
    if len(hook) > LIMITS["tiktok"]["visible"]:
        notes.append(f"hook runs past the {LIMITS['tiktok']['visible']}-char fold on "
                     "TikTok — the first clause is what most viewers see")
    if not tags:
        notes.append("no tags: add 3-5 searchable ones in brief.tags")
    return Listing(titles=titles_out, description="\n".join(desc_lines),
                   hashtags=tags, hook=hook, notes=notes)


def to_markdown(listing: Listing, name: str = "edit") -> str:
    out = [f"# {name} — listing", "", "## Hook", listing.hook, "", "## Titles",
           ""]
    for i, t in enumerate(listing.titles, 1):
        out.append(f"{i}. {t}  ({len(t)} chars)")
    out += ["", "## Description", "", "```", listing.description, "```", "",
            "## Hashtags", "", " ".join("#" + t for t in listing.hashtags), ""]
    if listing.notes:
        out += ["## Check before posting", ""]
        out += [f"- {n}" for n in listing.notes]
        out.append("")
    return "\n".join(out)


def to_post(listing: Listing, name: str = "edit", duration: float = 0.0) -> str:
    """The file you actually paste from, on the day.

    The listing document is for review; this is for the upload screen. Title
    first (in the order to try), then one caption block per platform — the same
    words, sized to what each one shows before "more" — then the tags on their
    own line so they are never buried inside a sentence.
    """
    tags = " ".join("#" + t for t in listing.hashtags)
    short_visible = LIMITS["reels"]["visible"]
    # The description already ends with its tag line. Strip any line that is
    # only hashtags before adding the canonical set back, or the caption carries
    # them twice — which is exactly what happened the first time this ran.
    body = [ln for ln in listing.description.strip().split("\n")
            if not (ln.strip() and all(w.startswith("#") for w in ln.split()))]
    lead = "\n".join(body).rstrip()
    first = _clip(lead.split("\n")[0], short_visible)
    out = [f"# POST — {name}", ""]
    if duration:
        out.append(f"_{duration:.1f}s · 1920x1080 · 30fps_")
        out.append("")
    out += ["## Title", ""]
    for i, t in enumerate(listing.titles, 1):
        out.append(f"{i}. **{t}**  ({len(t)} chars)")
    out += ["", "## Description", "",
            "Paste as-is (Reels / TikTok / Shorts all accept this):", "",
            "```", lead, "", tags, "```", "",
            f"The first {short_visible} characters are what shows before the "
            "cut, so that line has to stand alone:", "", "```", first, "```", "",
            "## Hashtags", "", tags, ""]
    if listing.notes:
        out += ["## Check before posting", ""] + [f"- {n}" for n in listing.notes]
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse

    from . import brief as briefs

    ap = argparse.ArgumentParser(description="title / description / hashtags")
    ap.add_argument("--brief", default="peter_gwen")
    ap.add_argument("--track", default="")
    ap.add_argument("--duration", type=float, default=43.0)
    ap.add_argument("--tag", action="append", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    b = briefs.load(a.brief)
    listing = write(b, a.duration, track=a.track, extra_tags=a.tag)
    md = to_markdown(listing, a.brief)
    print(md)
    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md)
        p.with_suffix(".json").write_text(json.dumps(listing.as_dict(), indent=1) + "\n")
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
