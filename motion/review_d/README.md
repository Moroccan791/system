# Motion graphics — Stage D review pack (Parts 4 + 5, vector-first)

All three videos were produced end-to-end by **`produce.py`** (authored
timeline → validate → render → composite → QC v2 → sound → review pack),
each with a **different theme config + seed**, all **PASS at level 0**
(the QC-failure fallbacks were not needed; they are unit-tested below).

| video | theme | seed | QC v2 | sound | notes |
|---|---|---|---|---|---|
| `stage1_test/final.mp4` | warm-minimal | 3 | PASS | 20 events (2.02/s, 1.11 accents/s), cuts 4/4, −14.1 LUFS, TP −2.8 | serif-italic typography from config only; brand accent still wins over theme accent (brand lock) |
| `stage2_test/final.mp4` | high-energy | 7 | PASS | 62 events (2.20/s, 1.56 accents/s), cuts 19/19, −14.1 LUFS, TP −3.2 | **vector-first**: SVG `hoop` (card) + `led` (full-bleed) replace the Stage-B photos; no ILLUSTRATIVE tag |
| `sartain_test/final.mp4` | bold-red | 21 | PASS | 24 events (1.96/s, 0.82 accents/s), cuts 2/2, −14.1 LUFS, TP −1.8 | theme accent matches the Sartain red |

## What's new in D

- **Vector graphics layer (user steer: Fiverr-style = animated vectors,
  not illustrated photos).** `vector` component in `stage.html`, native
  SVG scenes (`hoop`, `led`, `donut`, `arrow`, `burst`) animated
  deterministically from the frame clock (`draw/dash/pop/count ease-out`),
  in the video's accent, no ILLUSTRATIVE obligation. `decide.py` prefers
  vector for picturable nouns; the Stage-B generated-photo pipeline
  remains fallback only. Rationale: Remotion stays rejected (licence);
  a second renderer (Motion Canvas/Lottie) adds npm weight for zero
  output difference; downloads are egress-constrained anyway.
- **Themes as config** (`motion/themes/`, 5): palette, fonts
  (`fontMode`), radius, glow, speed, easing, transition order, sound
  pack. Stage-1 re-rendered with `warm-minimal` renders its taste words
  serif-italic purely from the config change — no code touched.
- **Auto-brand** (`brand.py`): samples the video, extracts the palette,
  picks the closest theme + accent override. On the budget footage it
  picks `bold-red` (hue 5 saturated cluster) with accent `#AC1709`;
  a timeline/brand accent always outranks the theme accent.
- **Prep** (`prep.py`): hook auto-pick scores sentences (number >
  question > strong claim > lead-in); on stage-2 it picks the "$2,500"
  opener (6.5). Dead pauses >0.55 s are compressed and word times
  remapped (found one 0.58 s pause in stage-2) — run BEFORE authoring.
- **`--seed` variation**: seeded randomisation of transitions, card
  sides, punch-ins, plate variants, sound rotation; every choice is
  logged in `decision_log.json` (beside each video). The three demos
  chose three different transition orders from three seeds.
- **Review pack per render** (`report.py`, Parts 5): frames 0–10 strip,
  1-frame/0.5 s contact sheet, 5-frame strips around every transition,
  `qc_full.json/.txt` (per word with ms offsets, per text element with
  px/%/contrast/face distance, per graphic enter/hold/idle/exit, per
  image/vector source/width/duration, per transition, longest no-change
  gap, sound totals + loudness). `qc_v2.txt` remains the PASS/FAIL gate.
- **Fallback chain** (`produce.py`): L0 full → L1 simplified (no
  inserts) → L2 plain poster captions — never a broken video; the level
  used is recorded. All three demos passed at L0.

## Honest limits

- Sartain accent density 0.82/s is a quiet, two-cut clip; the
  1.5–2.5/s overall figure holds on the 62/24/20-event videos, and
  the stage-2 caption-fade case is documented in `review_c/`.
- Face-safe placement is enforced at authoring (face-relative placement
  + reframe tracks) and QC measures final-pixel face overlap for
  captioned frames; graphic-vs-face is asserted via the ≥70%-width and
  no-corner rules rather than per-frame face boxes.
- 16:9 / 1:1 are accepted through the canvas config path
  (`probe` + `--canvas`, Stage-C tooling); the three demos are 9:16.
- Fallback levels 1–2 and the prep/brand helpers are covered by
  `tests/test_staged.py`; the full suite is green.

## Evidence in this pack

Per video: `final.mp4`, `sheet.jpg` (contact sheet + strip 0),
`qc_v2.txt` (gate), `qc_full.txt/.json` (Part-5 report),
`decision_log.json` (theme, seed, every seeded choice, fallback level),
`sound_log.json`; stage-2 also has transition strips.
`images/` holds the Stage-B photo choices the vector scenes replaced
(`scores.json` + chosen candidates) for comparison.
