# Motion-graphics layer (`motion/`)

Professional animated graphics as **HTML/CSS/SVG components**, rendered
frame-by-frame to transparent PNGs at 30 fps and composited over the
footage with ffmpeg's `overlay`. No ffmpeg drawtext/filter graphics
anywhere — ffmpeg only grades the footage, mixes audio and overlays.

Why not Remotion: its license is free only for ≤3-person teams and
automated/batch rendering is the paid "Automators" tier
($0.01/render, $100/mo minimum). This stack is hand-rolled JS +
Chromium (Apache-2.0 ecosystem), zero license cost, fully
deterministic: the same timeline JSON always produces the same frames.

## Pipeline

```
validate.py  →  render.mjs  →  composite.py  →  qc.py
(schema +      (Chromium       (grade, opening   (5 checks,
semantic        screenshots     blur-zoom, B/W    exit 1 on
rules)          PNG frames)     flashes, SFX)     any failure)
```

```bash
.venv/bin/python motion/validate.py motion/timelines/<name>.json
node motion/render.mjs motion/timelines/<name>.json work/<job>/frames
.venv/bin/python motion/composite.py <base.mp4> work/<job>/frames \
    motion/timelines/<name>.json work/<job>/out.mp4
.venv/bin/python motion/qc.py motion/timelines/<name>.json \
    <transcript.json> work/<job>/out.mp4 work/<job>/frames
.venv/bin/python motion/composite.py --sheet work/<job>/out.mp4 \
    motion/timelines/<name>.json work/<job>/demo   # contact sheet + strips
```

Setup (after a sandbox reset): `bash scripts/bootstrap.sh`, then
`npm install` inside `motion/` (puppeteer-core + @sparticuz/chromium;
the renderer extracts the bundled NSS libs to `/tmp/al2023` itself).

## Timeline JSON

The AI authors only this file; everything else is mechanical.
Schema: `motion/schema.json` (1080×1920 @ 30 fps, one accent colour +
black/white per video). Item types:

| type | what | stage |
|---|---|---|
| `poster` | word-stacked kinetic captions (keyword 5–7% of frame height in accent, connectives 2.5–3%, 9-frame pop entries, blur-out) | 1 |
| `chip` | accent label bar, 8-frame wipe + pop | 1 |
| `card` | full-screen claim card (serif/sans mixing allowed) | 1 |
| `fx` | `flare` / `leak` / `edge` light effects, footage-level `opening` (blur-zoom, first 8f) and `bwflash` | 1 |
| `pip` | proof/PiP photo card (~58% width, below the chin, white print frame, optional label pill; `illustrative: true` renders an ILLUSTRATIVE tag) | 2 |
| `broll` | B-roll window (92% width, aperture clip-open, Ken Burns drift, label over a bottom scrim) | 2 |
| `counter` | big accent number counting up with prefix/suffix, label under, lock-pop when it lands | 2 |
| `list` | accumulating plates (title pill + numbered dark plates, 6-frame-min stagger, latest badge lit) | 2 |
| `process` | step stack (title pill, numbered circles + connector, steps check off as the next one lands) | 2 |

Word kind `neon` (poster/card): hot emotional keywords render in an
electric red/blue with a 4-frame glow flicker at entry (opacity stays
clean for the semi-transparent QC); `serif` is the soft/reflective
variant. Media `src` paths may be repo-root-relative.

House rules enforced by `validate.py` + `qc.py`: word starts match
speech within ±40 ms; a visual change at least every 2.5 s (target
1.5 s); no text over faces (YuNet-checked against the poster zone);
text inside the 6% safe margin; no element semi-transparent for more
than 2 consecutive frames; poster `until` never cuts a spoken word;
no two same-type items overlapping in time.

Authoring rules: never put text across a shot change; don't repeat
the same component twice in a row; number/% → counter; "first,
second…" → list plates; process → step stack; strong claim →
full-screen card; concrete noun → PiP/B-roll (client footage first,
generated = marked illustrative); emotional word → neon or
serif-italic variant; default = poster captions.

## Decision rules (`decide.py`)

```bash
.venv/bin/python motion/decide.py <transcript.json> <out.json> [--accent #9BE82E]
```

Classifies every utterance by the first matching rule and emits a
draft timeline that passes `validate.py`: percent allocations /
sequence markers → process steps; comma enumerations → list plates
(a money headline in front also earns a counter); a headline money /
percent number → counter; a short strong claim → full-screen card;
everything else → poster captions with the keyword in the accent,
hot emotional words neon, soft ones serif-italic. Concrete nouns are
reported as PiP/B-roll candidates with timestamps (media choice stays
a human call — client footage first, generated stills always marked
illustrative). Poster stacks are repaired so neighbours abut but
never overlap; pacing gaps > 2.5 s are warned about at authoring
time. Tests: `tests/test_decide.py`; the rules were verified against
six real episode transcripts (all produce valid timelines) — on the
stage-2 test's own transcript they independently find the same
counter and list the test authors by hand.

## Stage-1 proof

`motion/demo/` — 10 s test on the MILK XP grading clip (accent
`#9BE82E`): poster captions, label chip, edge glow, B/W flash and a
full-screen claim card. QC: all 5 checks PASS (see `qc_report.txt`).

## Stage-2 proof

`motion/demo2/` — 28.8 s test on the budget-allocation scene (same
accent): every component in one cut — opening blur-zoom, posters
(with a neon CRAZY), $2,500 counter, TV/console/basketball list
plates, basketball-hoop PiP card, LED-lounge B-roll window (both
stills generated, both tagged ILLUSTRATIVE), wants chip, and the
NEEDS/WANTS/SAVE process stack lighting up as spoken. Base is two
shots joined at the cut (the middle shot carries the show's own
milk-jug gag, so it is skipped; no text crosses a shot change).
QC: all 5 checks PASS (see `qc_report.txt`). Timeline:
`motion/timelines/milk_budget_stage2.json`; stills:
`motion/test_assets/`.
