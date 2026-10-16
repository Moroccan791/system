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

Stage C additions: bases are built with `reframe.py` (face-tracked
9:16 crop of the 16:9 source — the speaker's face is never cut), and
every render finishes with `sound.py` (frame-exact synthesised CC0
sound design, −14 LUFS; see `review_c/README.md`):

```bash
.venv/bin/python motion/reframe.py work/<job>/seg_raw.mp4 work/<job>/seg_f.mp4
.venv/bin/python motion/sound.py work/<job>/timeline_fx.json \
    work/<job>/final.mp4 work/<job>/final_s.mp4 [--typing-sound off]
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

## Stage A — permanent rules (Parts 1–5 audit in `AUDIT.md`)

Pipeline gains a step: `transitions.py` runs before validation. It
detects hard cuts in the base (scene score ≥0.25, verified frame-by-
frame on this footage) and injects a rotating 8–10f transition
(flare/flash/leak/bwflash, peak on the cut) wherever the author did
not already place one, writing `<tl>.transitions.json`; composite
copies it next to the render as `<video stem>.transitions.json` and
QC checks against it.

```bash
.venv/bin/python motion/transitions.py <base.mp4> motion/timelines/<t>.json work/<job>/timeline_fx.json
.venv/bin/python motion/validate.py work/<job>/timeline_fx.json
node motion/render.mjs work/<job>/timeline_fx.json work/<job>/frames
.venv/bin/python motion/composite.py <base.mp4> work/<job>/frames work/<job>/timeline_fx.json work/<job>/final.mp4
.venv/bin/python motion/qc.py work/<job>/timeline_fx.json <transcript.json> work/<job>/final.mp4 work/<job>/frames
```

QC v2 = 12 checks (word lead −2f measured, text sizes ≥3% / keywords
6–8%, sampled contrast, pacing, dwell, idle, images, cuts, opening
frames 0–10, face zone, semi, margins). Engine rules now baked in:
no text under 58 px anywhere (plates grow, type never sinks),
keywords are ink-on-accent plates, words lead speech by 2 frames,
exits are 8f slide+blur, counters pulse 106%, every held graphic
drifts/shines/pulses, flare is a full-frame diagonal light leak,
B-roll is full-bleed (1.0–1.8 s) or a 60–70% card. One documented
interpretation (rule 1.12) lives in `AUDIT.md` — read it before
judging the cuts check. Stage A review pack: `motion/review_a/`
(3 source videos, QC v2 all-PASS).

## Stage D — themes, any video, vector-first (`produce.py`)

One command per video from Stage D on:

```bash
.venv/bin/python motion/produce.py <timeline.json> <base.mp4> \
    <transcript.json> work/<job> [--theme <name>] [--seed N] \
    [--typing-sound on|off]
```

`produce.py` injects transitions, validates, renders, composites,
runs QC v2 + sound, writes the Part-5 review pack and
`decision_log.json`, and only escalates the fallback chain
(L1 simplified → L2 plain poster captions) if QC fails — the level
is recorded; it never ships a broken video. Themes live in
`motion/themes/` (config only: palette, fonts, radius, glow, speed,
easing, transition order, sound pack); `brand.py` extracts a palette
from the footage and picks the closest theme + accent override when
no theme is given (a timeline accent always wins: brand lock).
`prep.py` (hook pick + pause tightening) runs before authoring.

**Vector components** (`vector` item, `mode: card|fullbleed`, **51
scenes** — full inventory in `MOTIONS.md`): animated SVG drawn
deterministically from the frame clock in the video accent — the
Fiverr-style look. `decide.py` auto-assigns scenes from spoken
triggers (Seeded clip position); generated photos (Stage B) are
fallback-only with the review flag. Scenes are authored in unit
width × canvas height — check composited frames, not just the
overlay stream. Stage D pack: `motion/review_d/`.

**Caption & typography packs** (catalogue in `MOTIONS.md`):
seven `captionStyle` engines (pop, karaoke, stretch, wiggle,
glide, bounce, neon-finish) via config or `decide.py
--caption-style`; hero lockups (whole-phrase animated posters,
one spoken word per beat, always zone-safe) and name-tag
lower-thirds (1.8–6 s, forbidden over slates). Posters also
support `behind: true` — the person stands IN FRONT of the
graphic (MediaPipe matte, `matte.py`, QC face-zone inverted) —
and `place3d` spatial tilt with an authored zoom-lock ramp.
Proofs: `demo_library/motions_demo2.mp4`, `behind_demo.mp4`.
