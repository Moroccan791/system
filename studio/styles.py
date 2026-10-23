"""The style registry — one name per look, and the house one is frozen.

Why this file exists: it is far easier to ruin a working system by "improving"
it than by writing a new one. The two delivered edits (`post2_bangla`,
`post2_zaalima`) were made by one particular arrangement of settings, and that
arrangement has to keep working exactly as it does, forever, while other looks
are added beside it.

So:

  * `house` is the system that made those two edits. Its entry is EMPTY on
    purpose — every field is None, which means "whatever the pipeline already
    does". Nothing about a house render changes because a style module exists.
  * every other style is a table of explicit parameters plus, at most, one hook
    into a module of its own. A style may ADD a layer; it may not reach into the
    house path and alter it.
  * `--style` resolves through this registry. An unknown name is an error that
    lists what exists, rather than a silent fallback to the house look — a
    fallback would render the wrong video and say nothing.

    python -m studio.styles --list
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FROZEN_NOTE = (
    "the arrangement that produced post2_bangla and post2_zaalima; "
    "do not edit the numbers, add a new style instead"
)


@dataclass(frozen=True)
class Style:
    name: str
    label: str
    note: str = ""
    # picture and pacing. None = the pipeline's own default, unchanged.
    behaviour: str | None = None
    design: str | None = None
    silence_ms: float | None = None
    format: str = "landscape"
    accent_at: float | None = None
    # which machinery renders it
    type_engine: str = "cards"          # cards (house) | ref2
    grade: str = "premium"              # premium | ref2
    fx: tuple[str, ...] = ()            # halation, chroma, ghost, jolt
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# the frozen one
# ---------------------------------------------------------------------------
HOUSE = Style(
    name="house",
    label="House",
    note=FROZEN_NOTE,
    behaviour=None,      # the director's default behaviours, as delivered
    design=None,         # the sound design those two edits were cut with
    silence_ms=None,
    format="landscape",
    accent_at=None,
    type_engine="cards",
    grade="premium",
    fx=(),
)

# ---------------------------------------------------------------------------
# everything else
# ---------------------------------------------------------------------------
REGISTRY: dict[str, Style] = {
    "house": HOUSE,
    # The Gwen-death system. Kept because it is built and tested, not because it
    # is the direction: its type accumulates, which was the wrong call for a
    # lyric-led edit. Selected explicitly, never by default.
    "reference2": Style(
        name="reference2",
        label="Reference 2 — Gwen death",
        note="stack type, crimson bed, silence holes, dark teal grade",
        behaviour="lyric",
        type_engine="ref2",
        grade="ref2",
        fx=("halation", "chroma", "ghost", "jolt"),
    ),
}


def get(name: str | None) -> Style:
    """Resolve a style name. No name means the house system, exactly as before."""
    if not name:
        return HOUSE
    if name not in REGISTRY:
        raise KeyError(
            f"no style {name!r}. Known styles: {', '.join(sorted(REGISTRY))}\n"
            f"  add one in studio/styles.py — a table, not a rewrite")
    return REGISTRY[name]


def names() -> list[str]:
    return sorted(REGISTRY)


PACKS = Path(__file__).resolve().parent / "stylepacks"


def pack(name: str = "house_v1") -> dict:
    """Load a frozen style pack — the copy of a system, not a description of it."""
    import json

    p = PACKS / f"{name}.json"
    if not p.exists():
        raise KeyError(f"no pack {name!r} in {PACKS}")
    return json.loads(p.read_text())


def show_pack(name: str = "house_v1") -> str:
    """Everything needed to re-run the frozen system, plus a live check that the
    delivered files are still the files that pack describes."""
    import hashlib
    from pathlib import Path as _P

    d = pack(name)
    out = [f"{d['version']} — frozen {d['frozen_on']}",
           f"  {d['_what']}", ""]
    out.append("engine")
    for k, v in d["engine"].items():
        out.append(f"  {k:20s} {v}")
    out.append("")
    for e in d["edits"]:
        out.append(f"edit  {e['name']}  ({e['font']}, #{e['colour']}, "
                   f"{e['window']['start']}->{e['window']['end']}s)")
        fp = e["fingerprint"]
        out.append(f"      {fp['cuts']} cuts over {fp['duration']}s at {fp['bpm']} BPM")
        for act in ("build", "drop", "out"):
            a = fp[act]
            extra = "".join(f"  {k} {a[k]}" for k in ("flash", "whip", "ramp") if k in a)
            out.append(f"      {act:6s} {a['cuts']:3d} cuts  {a['seconds']:6.2f}s  "
                       f"median {a['median']:.2f}s{extra}")
        f = _P(e["delivered"])
        if f.exists():
            h = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
            ok = "matches" if h == e["sha256_12"] else f"CHANGED ({h})"
            out.append(f"      delivered: {e['delivered']} — {ok}")
        else:
            out.append(f"      delivered: {e['delivered']} — not in this checkout")
        out.append("")
    out.append("re-run with:  --style house   (or no --style at all)")
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="the look registry")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pack", default=None, metavar="NAME",
                    help="print a frozen style pack and verify its delivered files")
    a = ap.parse_args(argv)
    if a.pack:
        print(show_pack(a.pack))
        return 0
    if a.list:
        for n in names():
            st = REGISTRY[n]
            print(f"{n:12s} {st.label}")
            if st.note:
                print(f"{'':12s} {st.note}")
            print(f"{'':12s} type={st.type_engine} grade={st.grade} "
                  f"fx={','.join(st.fx) or '-'} behaviour={st.behaviour or 'default'}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
