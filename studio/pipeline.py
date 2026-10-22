"""One command per video. The standing workflow, in code.

The sequence is fixed because it was established by the work, not by taste:

    video + audio + the lyric as text
        -> research the fandom            (studio/brief.py — a gate, not a note)
        -> place the words                (studio/captions.py, preview first)
        -> choose the face                (studio/fonts.py, assets/fonts/edit)
        -> render                         (studio/produce.py, one renderer)

Nothing here is guessed: the out-point comes from the last word, the start comes
from the first word, the words come from the text, the face comes from a choice.
`--dry-run` stops after the caption sheet and the plan — the approval step before
four minutes of encoding are spent.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

from . import fonts
from .captions import (cards_from_words, coverage, parse_lines, preview,
                       save_cards, to_script)
from .ends import out_point
from .grid import analyse as analyse_track
from .lyrics import transcribe_robust
from .shots import analyse as analyse_source


def _probe_audio(path: str) -> float:
    import imageio_ffmpeg

    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"could not read the duration of {path}")


def _asr_for(track: str, duration: float) -> list[dict]:
    """Transcribe once and cache by file identity.

    The ASR is the slowest step, and two passes over the same audio disagree by
    up to a second. Captions are approved from one transcript, so the render has
    to use that same transcript rather than transcribe again and shift.
    """
    st = Path(track).stat()
    key = hashlib.sha1(f"{track}:{st.st_size}:{int(st.st_mtime)}"
                       .encode()).hexdigest()[:12]
    cache = Path("work/studio") / f"asr_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    words = transcribe_robust(track, 0.0, duration)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words, indent=1) + "\n")
    return words


def _bar_floor(grid, t: float) -> float:
    beats = grid.beats(max(0.0, t))
    return max(0.0, grid.t(math.floor(beats / 4.0) * 4.0))


def run(video: str, audio: str, captions: str, out: str,
        start: float | None = None, font: str | None = None,
        dry_run: bool = False, preset: str = "medium", crf: int = 18,
        preview_path: str | None = None, accent: str | None = None,
        accent_colour: str | None = None, brief_name: str = "peter_gwen",
        tags: list[str] | None = None) -> dict:
    grid = analyse_track(audio)
    duration = min(grid.duration, _probe_audio(audio))
    lines = parse_lines(captions)
    if not lines:
        raise SystemExit(f"no captions in {captions}")

    words = _asr_for(audio, duration)
    cards = cards_from_words(lines, audio, 0.0, duration, asr=words)
    if not cards:
        raise SystemExit("no sung words found — check the lyric against the audio")

    # start: one bar of air before the first word, on a bar line
    first = cards[0]["start"]
    start = start if start is not None else _bar_floor(grid, first - 1.0)
    cards = [c for c in cards if c["start"] >= start - 1e-6]
    last = cards[-1]["end"]
    end = out_point(last, grid, tail=1.2, ceiling=duration)

    report = {
        "start": round(start, 2), "end": round(end, 2),
        "duration": round(end - start, 2),
        "first_word": round(first, 2), "last_word": round(last, 2),
        "lines": len(lines), "cards": len(cards),
        "coverage": coverage(cards, lines),
        "font": (font or fonts.config().get("main")),
    }

    sheet = preview_path or str(Path(out).with_suffix(".cards.jpg"))
    preview(cards, sheet)
    cards_file = Path(out).with_suffix(".cards.json")
    cards_file.parent.mkdir(parents=True, exist_ok=True)
    save_cards(cards, cards_file)
    script = Path(out).with_suffix(".script.json")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(json.dumps({"bpm": grid.bpm,
                                  "cards": to_script(cards, grid.bpm,
                                                     origin=start)},
                                 indent=1) + "\n")
    # The listing is written from the same brief the shots were chosen from, and
    # it is written here — before the render — so it can be reviewed with the
    # card sheet rather than scrambled together at posting time.
    from . import brief as briefs
    from . import publish

    studio_brief = briefs.load(brief_name)
    listing = publish.write(studio_brief, end - start,
                            track=Path(audio).stem.replace("_", " "),
                            extra_tags=tags)
    listing_path = Path(out).with_suffix(".publish.md")
    listing_path.write_text(publish.to_markdown(listing, studio_brief.title))
    report["publish"] = listing.as_dict()
    report["publish_file"] = str(listing_path)

    report["sheet"] = sheet
    report["script"] = str(script)
    report["cards_file"] = str(cards_file)

    # The face is the operator's decision, every time. There is no "default
    # font" in this pipeline: a render that quietly picks one is a render nobody
    # chose, and the choice is part of the style. Without --font the job stops
    # here and prints what is available, with the specimen if it exists.
    if not font and not dry_run:
        faces = sorted(fonts.edit_faces())
        report["needs_font"] = True
        print("font: not chosen — refusing to render.")
        print("  faces in assets/fonts/edit/: " + ", ".join(faces))
        print(f"  current family: {fonts.config()}")
        print("  pick one:  --font <face> [--accent <face>] [--accent-colour RRGGBB]")
        print("  the sheet to choose from: studio/out/font_choice.jpg")
        return report

    if font:
        col = None
        if accent_colour:
            h = accent_colour.lstrip("#")
            col = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        fonts.set_family(font, accent, col)

    if dry_run:
        from . import director
        from .plan import build_directed_plan, summarise

        src = analyse_source(video, None)
        from .director import DIRECTIONS

        direction = DIRECTIONS.get(brief_name, director.LINE_DIRECTION)
        plan = build_directed_plan(
            grid, src,
            director.segments_for(grid, src, cards, end, start, direction), start)
        report["plan"] = summarise(plan).splitlines()
        print(summarise(plan))
        print(f"cards {len(cards)}  {start:.2f} -> {end:.2f}s  "
              f"({end - start:.2f}s)  sheet {sheet}")
        return report

    from .produce import main as produce

    produce(["--track", audio, "--source", video, "--captions", captions,
             "--cards", str(cards_file), "--brief", brief_name,
             "--start", f"{start:.3f}", "--end", f"{end:.3f}",
             "--script", str(script), "--out", out, "--direct",
             "--preset", preset, "--crf", str(crf)])

    # Verification is part of the job, not a follow-up. The render is checked
    # against its OWN audio: what the words are, and whether they are audible
    # where they are on screen. A line whose best evidence sits somewhere else
    # in the song fails, and the take does not ship.
    from . import sync

    sc = json.loads(script.read_text())
    bpm = float(sc.get("bpm", grid.bpm))
    timed = [{"start": c["beat"] * 60.0 / bpm,
              "end": c.get("until", c["beat"]) * 60.0 / bpm,
              "text": c["text"], "line": c.get("line", -1)}
             for c in sc["cards"]]
    rows = sync.check(timed, sync.window_texts(out, report["duration"]))
    print(sync.report(rows))
    Path(out).with_suffix(".sync.txt").write_text(sync.report(rows) + "\n")
    report["sync"] = {r["text"]: r["state"] for r in rows}
    report["sync_failures"] = [r["line"] for r in rows if r["state"] == "FAIL"]
    return report


def main_cli(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="video + audio + lyric -> edit")
    ap.add_argument("--video", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--captions", required=True,
                    help="the lyric, one sung line per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--font", default=None, help="a face from assets/fonts/edit")
    ap.add_argument("--accent", default=None,
                    help="face for the one accent word on a card")
    ap.add_argument("--accent-colour", default=None, help="RRGGBB")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--brief", default="peter_gwen",
                    help="which researched brief this edit is cut for")
    ap.add_argument("--tag", action="append", default=None,
                    help="extra hashtag, no # (repeatable)")
    ap.add_argument("--dry-run", action="store_true",
                    help="stop after the caption sheet and the plan")
    a = ap.parse_args(argv)
    rep = run(a.video, a.audio, a.captions, a.out, a.start, a.font,
              a.dry_run, a.preset, a.crf, accent=a.accent,
              accent_colour=a.accent_colour, brief_name=a.brief,
              tags=a.tag)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
