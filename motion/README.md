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
| `pip`, `broll`, `counter`, `list`, `process` | stage 2 — not built yet | 2 |

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

## Stage-1 proof

`motion/demo/` — 10 s test on the MILK XP grading clip (accent
`#9BE82E`): poster captions, label chip, edge glow, B/W flash and a
full-screen claim card. QC: all 5 checks PASS (see `qc_report.txt`).
Stage 2 (components 4/6/7/8/9 + formalised decision rules) starts
only after approval of this contact sheet.
