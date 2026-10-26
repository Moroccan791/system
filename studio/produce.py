"""One command: track + footage + words -> an overedit.

    python -m studio.produce \
        --track work/studio/test_score.wav \
        --source clips/amazing_spiderman.mp4 \
        --script studio/scripts/example.json \
        --start 12.0 --end 34.0 \
        --out work/studio/edit.mp4

Writes the edit, plus `<out>.plan.json` and `<out>.report.json` next to it, so a
render can be explained after the fact: every cut, which shot fed it, where it
landed on the grid, and what the analysis found.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .compose import OUT_FPS, OUT_H, OUT_W, render

from . import frame as _frame
from .grid import analyse as analyse_track
from .plan import build_plan, summarise
from .captions import ACCENT_WORDS as ACCENT
from .shots import analyse as analyse_source


def report(plan, grid, src) -> dict:
    acts = {}
    for cut in plan.cuts:
        a = acts.setdefault(cut.act, {"cuts": 0, "seconds": 0.0, "shots": set(),
                                      "flash": 0})
        a["cuts"] += 1
        a["seconds"] += cut.dur
        a["shots"].add(cut.shot)
        a["flash"] += int(cut.flash)
    for a in acts.values():
        a["seconds"] = round(a["seconds"], 2)
        a["shots"] = len(a["shots"])

    # on-grid check: how far each cut lands from the nearest 16th
    import math

    grid_errors = []
    for cut in plan.cuts:
        beat = (cut.out_start) / (60.0 / grid.bpm)
        nearest = round(beat * 4) / 4
        grid_errors.append(abs(beat - nearest) * 60.0 / grid.bpm)
    return {
        "bpm": round(grid.bpm, 2),
        "duration": round(plan.duration, 3),
        "size": f"{_frame.size()[0]}x{_frame.size()[1]}@{OUT_FPS}",
        "cuts": len(plan.cuts),
        "acts": acts,
        "median_cut": round(sorted(c.dur for c in plan.cuts)[len(plan.cuts) // 2], 3)
        if plan.cuts else 0,
        "min_cut": round(min((c.dur for c in plan.cuts), default=0), 3),
        "max_cut": round(max((c.dur for c in plan.cuts), default=0), 3),
        "distinct_shots_used": len({c.shot for c in plan.cuts}),
        "shots_available": len(src.shots),
        "grid_error_ms_median": round(1000 * sorted(grid_errors)[len(grid_errors) // 2], 1)
        if grid_errors else 0,
        "grid_error_ms_max": round(1000 * max(grid_errors), 1) if grid_errors else 0,
        "sections": [s.as_dict() for s in grid.sections],
    }


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="render an overedit")
    ap.add_argument("--track", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", default=None, help="json list of {beat,text,accent}")
    ap.add_argument("--cards", default=None,
                    help="json list of approved cards (start/end/text/line) — "
                         "used verbatim, no second transcription")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--captions", default=None,
                    help="the lyric as text, one sung line per line — the words "
                         "on screen are placed from this, never guessed")
    ap.add_argument("--timed", default=None,
                    help="lyric file whose lines carry their own times "
                         "(mm:ss.mmm text) — the path for a vocal the ASR cannot "
                         "read, such as Hindi or Bangla sung in roman script")
    ap.add_argument("--start", type=float, default=0.0, help="track start, seconds")
    ap.add_argument("--end", type=float, default=None, help="track end, seconds")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--behaviour", default=None,
                    help="lyric | crescendo | mosaic")
    ap.add_argument("--accent-at", type=float, default=None, metavar="SEC",
                    help="edit time of the song's real drop — the impact, sub, "
                         "tape-stop and the silence all go here")
    ap.add_argument("--design", default=None,
                    help="sound design gesture into the drop: tape_stop")
    ap.add_argument("--silence-before-drop", type=float, default=None,
                    metavar="MS",
                    help="cut the music dead this many ms before the drop "
                         "(the 'no dialogue' version of a cold open)")
    ap.add_argument("--no-sfx", action="store_true",
                    help="track only, no beat-locked sound design")
    ap.add_argument("--direct", action="store_true",
                    help="let the lyric choose the shots (studio/director.py) "
                         "instead of the shot scorer")
    ap.add_argument("--brief", default=None,
                    help="brief + direction set name. NO DEFAULT: it used to be "
                         "'peter_gwen', so a render that did not name a brief "
                         "silently got the Peter & Gwen shot table — 17 of a "
                         "451s pack's 100 shots, and nothing past 3:07")
    ap.add_argument("--direction", default=None,
                    help="line-direction set in director.DIRECTIONS "
                         "(default: the brief name, else peter_gwen)")
    ap.add_argument("--no-look", action="store_true",
                    help="skip push-in / entry settle / grain")
    ap.add_argument("--no-premium", action="store_true",
                    help="skip colour matching and the filmic grade")
    ap.add_argument("--no-watermark", action="store_true",
                    help="leave the account handle off the frame (it is read "
                         "from assets/fonts/family.json)")
    ap.add_argument("--bed", default=None,
                    help="reference2: the phrase held behind the picture "
                         "(default: the lyric's own most-repeated short phrase)")
    ap.add_argument("--style", default=None,
                    help="a look from studio/styles.py (default: house)")
    ap.add_argument("--map", default=None, metavar="FILE",
                    help="a hand-written cut map (studio/segments.py) — every "
                         "cut chosen by watching, with per-cut speed")
    ap.add_argument("--emphasis", default=None, metavar="FILE",
                    help="words to accent for THIS video, one per line or "
                         "comma separated. The general list knows nothing "
                         "about this song.")
    ap.add_argument("--bpm", type=float, default=None,
                    help="force the tempo (a ballad read as its own double is "
                         "the usual reason: Ghost is 71.75, the detector says 143.8)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="render at a fraction of the delivery size (memory "
                         "budget, not a style) — 0.6667 gives 1280x720")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--crf", type=int, default=None,
                    help="default 18 clean, 23 when the look layer is on: grain "
                         "costs ~5x the bitrate and a 43s file hit 137MB at 18")
    a = ap.parse_args(argv)
    if a.crf is None:
        a.crf = 23 if not a.no_look else 18

    from . import frame as _frame

    if a.scale != 1.0:
        _frame.set_scale(a.scale)
        print(f"scale {a.scale:g} -> {_frame.size()[0]}x{_frame.size()[1]}")

    t0 = time.time()
    grid = analyse_track(a.track, a.end)
    if a.emphasis:
        from .captions import set_emphasis

        raw = Path(a.emphasis).read_text()
        words = [w for line in raw.splitlines() for w in line.replace(",", " ").split()]
        got = set_emphasis(words)
        print(f"emphasis: {len(got)} words — {', '.join(sorted(got))}")

    if a.bpm:
        before = grid.bpm
        grid = grid.retimed(a.bpm)
        print(f"tempo forced: {before:.2f} -> {grid.bpm:.2f} BPM "
              f"(phase {grid.phase:.3f}s)")
    print(f"track: {grid.bpm:.1f} BPM, {len(grid.sections)} sections, "
          f"beat0 {grid.phase:.3f}s")
    for s in grid.sections:
        print(f"  {s.label:6s} {s.start:6.2f}-{s.end:6.2f}")
    # the SOURCE is always analysed in full: truncating it at the track
    # end hides every shot after that point, which is most of a pack
    src = analyse_source(a.source, None)
    print(f"source: {len(src.shots)} shots, {src.duration:.2f}s")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # A style that brings its own planner owns the whole timeline. Both of the
    # built styles are music-and-picture: they do not consult the lyric to
    # decide shots, which is why they run before the caption guard.
    _own_planner = {"barrage": "barrage", "longtake": "longtake",
                    "cold_read": "coldread", "hymn": "hymn",
                    "hype": "hype"}.get(a.style)
    if _own_planner:
        from importlib import import_module

        mod = import_module(f"studio.{_own_planner}")
        if a.map:
            # An editor's cut, not a scorer's: the map names every shot.
            from . import segments as _segments

            picks = _segments.load(a.map)
            plan = _segments.build(grid, src, picks, a.start, a.end, a.seed,
                                   grade=getattr(mod, "GRADE", None))
            print(_segments.summarise(picks))
        else:
            plan = mod.build(grid, src, a.start, a.end, a.seed)
            print(mod.summarise(plan))

        # The words. A style that plans its own shots still puts the lyric on
        # screen, so the caption sources have to be read HERE too — before this,
        # --captions was silently ignored by every own-planner style and the
        # edit rendered clean with no type at all.
        from .captions import (cards_from_words, from_timed, parse_lines,
                               parse_timed)

        placed = None
        if a.cards:
            raw = json.loads(Path(a.cards).read_text())
            placed = raw.get("cards", []) if isinstance(raw, dict) else raw
        elif a.timed:
            # Line-level cards, not word-level. `from_timed` splits a line into
            # per-word cards, which suits the house's one-word beats; these
            # styles set a FRAGMENT — the whole line — and kill it on the cut.
            # Passing words produced "is a" alone on screen, which is not a
            # fragment, it is half a sentence.
            lines = parse_timed(a.timed)
            placed = []
            for i, (t0, t1, text) in enumerate(lines):
                if not text.strip():
                    continue
                nxt = lines[i + 1][0] if i + 1 < len(lines) else grid.duration
                placed.append({"start": t0, "end": min(t1 or nxt, nxt),
                               "text": text.strip(), "line": i})
        elif a.captions:
            lines = parse_lines(a.captions)
            placed = cards_from_words(lines, a.track, a.start,
                                      grid.duration - a.start)
        if placed:
            # placed[] is in TRACK seconds; a style works in EDIT seconds
            placed = [dict(c, start=round(c["start"] - (a.start or 0.0), 3),
                           end=round(c["end"] - (a.start or 0.0), 3))
                      for c in placed]
            print(f"words: {len(placed)} placed from "
                  f"{'cards' if a.cards else 'timed lines' if a.timed else 'the lyric'}")
            cards = placed
            a.cards = "__placed__"

        if a.cards:
            # These styles still DRAW type when a card table is supplied; they
            # just do not let it choose the shots. The table is copied into the
            # script the compositor reads, unchanged.
            from .captions import to_script

            if a.cards == "__placed__":
                cards = placed
            else:
                raw = json.loads(Path(a.cards).read_text())
                cards = raw.get("cards", []) if isinstance(raw, dict) else raw
            card_until = getattr(mod, "type_until", None)
            stop = card_until(plan) if card_until else None
            # A card FILE is in track seconds; `placed` above is already in
            # edit seconds. Only the file needs the window start subtracted —
            # doing it twice moves every card before frame one.
            if a.cards == "__placed__":
                origin_s = 0.0
            else:
                origin_s = a.start or 0.0
            cards = [c for c in cards if (c["start"] - origin_s) < (stop or 1e9)]
            # A style may reshape its own type — cold_read kills a fragment on
            # the cut, hymn holds a line across cuts, hype allows one word.
            shape = getattr(mod, "shape_cards", None)
            if shape:
                cards = [dict(c, start=round(c["start"] - origin_s, 3),
                              end=round(c["end"] - origin_s, 3))
                         for c in cards]
                cards = shape(cards, plan)
            script_path = Path(a.script) if a.script else out.with_suffix(".script.json")
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(json.dumps(
                {"bpm": grid.bpm,
                 # origin=0: `shape_cards` already shifted the table into
                 # edit time, so subtracting the window start again would put
                 # every card before frame one (it did: beats of -30).
                 "cards": to_script(cards, grid.bpm, {}, origin=0.0)},
                indent=1) + "\n")
            a.script = str(script_path)
            if stop:
                print(f"type: {len(cards)} cards, stops at {stop:.1f}s "
                      f"({(1 - stop / plan.duration) * 100:.0f}% of the edit is clean)")
    elif a.direct:
        from . import director
        from .captions import (cards_from_words, from_timed, parse_lines,
                               parse_timed, to_script)
        from .ends import out_point
        from .plan import build_directed_plan

        if not (a.captions or a.cards or a.timed):
            raise SystemExit(
                "refusing to render: --direct needs --captions, --timed or "
                "--cards. The words on screen are an input; a guessed lyric on "
                "correct timings is still the wrong lyric.")

        # Place the captions across the WHOLE tail of the track, not just the
        # window: the out-point is derived from the last placed word, so the
        # window has to be able to grow past where we thought it ended.
        if a.cards:
            # The cards were placed and approved upstream. Re-deriving them here
            # would transcribe again, disagree by up to a second, and silently
            # render something the operator never saw.
            raw = json.loads(Path(a.cards).read_text())
            # A card file can say it has already been through polish(). Running
            # it twice leads every word by 2x LEAD and doubles the final tail,
            # which is how a 3.3s last card became 4.5s.
            if isinstance(raw, dict):
                cards = raw.get("cards", [])
                already_polished = bool(raw.get("polished"))
            else:
                cards = raw
                already_polished = False
        elif a.timed:
            # The operator supplied the line times. No transcript is consulted:
            # onsets place the words inside each line, which is language-blind.
            lines = [t for _a, _b, t in parse_timed(a.timed)]
            cards = from_timed(a.track, parse_timed(a.timed),
                               grid.duration - a.start)
            # These lines carry their own times, so polish() would move words
            # that are already placed. It was never set on this branch, so
            # --timed crashed with UnboundLocalError before it could render.
            already_polished = True
        else:
            lines = parse_lines(a.captions)
            cards = cards_from_words(lines, a.track, a.start,
                                     grid.duration - a.start)
        if not cards:
            raise SystemExit("refusing to render: no vocal found for the captions")
        # lead into the syllable, hold through breaths — see captions.polish
        from .captions import lint, polish, timeline
        if not already_polished:
            cards = polish(cards)
        print(timeline(cards))
        problems = lint(cards)
        if problems:
            print("caption lint:")
            for p_ in problems:
                print("  " + p_)
        last_word = cards[-1]["end"]
        if a.end is None:
            a.end = out_point(last_word, grid, tail=1.2, ceiling=grid.duration)
            print(f"end: {a.end:.2f}s  (last placed word ends {last_word:.2f}s, "
                  f"+1.2s tail, snapped up to the bar)")
        elif a.end < last_word:
            raise SystemExit(
                f"refusing to render: --end {a.end:.2f}s is before the last "
                f"caption ({last_word:.2f}s) — the edit would cut the line")
        cards = [c for c in cards if c["start"] < a.end - 1e-3]

        script_path = Path(a.script) if a.script else out.with_suffix(".script.json")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            json.dumps({"bpm": grid.bpm,
                        "cards": to_script(cards, grid.bpm, ACCENT,
                                           origin=a.start)}, indent=1) + "\n")
        a.script = str(script_path)
        src_desc = (f"{len(lines)} lines" if a.captions and not a.cards
                    else "approved upstream")
        print(f"captions: {len(cards)} cards from {src_desc} -> {script_path}")

        name = a.direction or a.brief
        local_fill, exhale_shot, settle = False, None, False
        if name in director.DIRECTIONS:
            direction = director.DIRECTIONS[name]
            tail_pool = director.TAILS.get(name)
        else:
            # No hand-written table for this lyric. Falling back to
            # LINE_DIRECTION is what made a 451s pack yield 17 of its 100 shots:
            # that table belongs to one video and names no shot above 35.
            # Build the pools from the pack itself so the edit uses all of it.
            # line texts, in order, so a repeated hook can be found
            by_line: dict[int, list[str]] = {}
            for c in cards:
                by_line.setdefault(c["line"], []).append(c.get("text", ""))
            line_texts = [" ".join(by_line[k]).strip() for k in sorted(by_line)]
            n_lines = len(line_texts) or 1
            direction = director.pack_direction(src, line_texts)
            # breaths stay where the walk is, and the edit ends on the pack's
            # own last image rather than shot 34 of another video
            local_fill = settle = True
            held = direction[max(direction)]["shots"][0]
            exhale_shot = director.pack_exhale(src, exclude=held)
            tail_pool = director.pack_fill(src, at="end",
                                           exclude=exhale_shot[0])
            print(f"direction: none for {name!r} — pools built from the pack "
                  f"({n_lines} lines over {len(src.shots)} shots)")
        segs = director.segments_for(grid, src, cards, a.end, a.start, direction,
                                     director.INTROS.get(name),
                                     tail_pool,
                                     behaviour=a.behaviour,
                                     word_pool=director.WORD_POOLS.get(name),
                                     max_cuts=1 if a.style == "reference2" else None,
                                     local_fill=local_fill,
                                     exhale_shot=exhale_shot,
                                     settle=settle)
        plan = build_directed_plan(grid, src, segs, a.start)
    else:
        plan = build_plan(grid, src, a.start, a.end, a.seed)
    if not _own_planner:
        print(summarise(plan))

    rep = report(plan, grid, src)
    out.with_suffix(".plan.json").write_text(json.dumps(plan.as_dict(), indent=1) + "\n")
    out.with_suffix(".report.json").write_text(json.dumps(rep, indent=1) + "\n")

    from .sound import cues_for

    cues = cues_for(plan, a.design, a.accent_at)
    rep["sound"] = {"cues": len(cues),
                    "by_kind": {k: sum(1 for c in cues if c.kind == k)
                                for k in ("riser", "tape_stop", "impact",
                                          "sub_drop", "whoosh", "tick", "swell")},
                    "on_grid_problems": __import__("studio.sound",
                                                   fromlist=["x"]).check_on_grid(
                                                        cues, plan)}
    out.with_suffix(".report.json").write_text(json.dumps(rep, indent=1) + "\n")

    if a.plan_only:
        print(f"plan-only: {out} not rendered")
        return 0

    accent_at = a.accent_at
    if accent_at is not None:
        print(f"accent: the drop is at {accent_at:.2f}s of the edit")

    gap = None
    if a.silence_before_drop and accent_at is not None:
        gap = (max(0.0, accent_at - a.silence_before_drop / 1000.0), accent_at)
        print(f"silence: {a.silence_before_drop:.0f}ms of nothing before "
              f"{accent_at:.2f}s")
    elif a.silence_before_drop:
        drop = next((c for c in plan.cuts if c.act == "drop"), None)
        if drop is not None and drop.out_start < 0.05:
            # the edit starts ON the drop, so there is no "before" to cut. Saying
            # so is better than printing a 600ms silence that never happens.
            print("silence: skipped — this edit begins on the drop, so there is "
                  "nothing before it to go quiet")
        elif drop is not None:
            end = drop.out_start
            start = max(0.0, end - a.silence_before_drop / 1000.0)
            gap = (start, end)
            print(f"silence: {a.silence_before_drop:.0f}ms of nothing "
                  f"before the drop at {end:.2f}s")

    silences = None
    if a.style == "reference2":
        from . import ref2

        # holes are in EDIT time (0 = first frame of the edit), which is what the
        # mix and the picture both count in — not track time.
        cuts = [c.out_start for c in plan.cuts]
        silences = ref2.holes(0.0, plan.duration, cuts=cuts,
                              accent_at=a.accent_at)
        # A hole placed by the style and a hole placed by --silence-before-drop
        # must not overlap: the second one would punch a gap inside a gap and
        # the longer silence would be read as a rendering fault.
        if gap is not None:
            silences = [g for g in silences
                        if g[1] <= gap[0] or g[0] >= gap[1]]
        for g0, g1 in silences:
            print(f"silence: {g0:.2f}-{g1:.2f}s ({(g1 - g0):.2f}s of nothing)")
        ghosts = ref2.ghost_cuts(plan.cuts)
        print("ghosting: cuts " + ", ".join(str(i) for i in ghosts)
              + " (double exposure on entry)")

    render(plan, a.source, a.track, out, a.script,
           progress=lambda m: None, preset=a.preset, crf=a.crf,
           sfx=not a.no_sfx, look=not a.no_look,
           # A style that brings its own grade must not be run through premium:
           # premium matches every shot to the pack median and then applies the
           # house curve, which is exactly the look barrage contradicts. Passing
           # premium=False hands the grading to plan.grade_for, which is where
           # the style's numbers live.
           premium=(not a.no_premium) and a.style not in (
               "barrage", "longtake", "cold_read", "hymn", "hype"),
           gap=gap, design=a.design, accent_at=accent_at,
           watermark=not a.no_watermark, style=a.style, silences=silences,
           bed_text=a.bed, ghost_cuts=ghosts if a.style == "reference2" else None)
    print(f"sound: {len(cues)} cues "
          f"({', '.join(f'{k} {v}' for k, v in rep['sound']['by_kind'].items() if v)})")
    print(f"wrote {out}  ({plan.duration:.2f}s, {time.time() - t0:.0f}s to build)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
