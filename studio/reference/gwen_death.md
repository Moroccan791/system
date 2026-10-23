# Reference decomposition — "Gwen Stacy's death" / LOVE ME

Source file: `Gwen Stacys death is one of the most heartbreaking moments in superhero cinema. Her intelligenc.mp4`
58.47 s · 1280×532 (2.41:1 picture, letterboxed in a 16:9 file) · 30 fps · H.264 · AAC · 3.7M likes.

Everything below was measured from the file — scene-change detection at
threshold 0.25, 10 fps frame differencing, white/red type masks, 10 ms RMS
envelope and spectral-flux onsets at 16 kHz, and 2 fps grade statistics. Where a
number is an estimate it says so.

This is the second reference for the studio. The first
(`spiderman_analysis.md`) is a **beat edit**: 45% of it contains almost no
cutting, then 30 cuts in 16 s. This one is not. The two are kept apart on
purpose — see "What it implies for the engine".

## Structure — 21 shots in 58.5 s

| # | in | out | len | | # | in | out | len |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.00 | 1.67 | 1.67 | | 12 | 27.80 | 28.27 | 0.47 |
| 2 | 1.67 | 2.90 | 1.23 | | 13 | 28.27 | 29.17 | 0.90 |
| 3 | 2.90 | 5.57 | 2.67 | | 14 | 29.17 | 30.17 | 1.00 |
| 4 | 5.57 | 5.93 | 0.37 | | 15 | 30.17 | 33.40 | 3.23 |
| 5 | 5.93 | 6.63 | 0.70 | | 16 | 33.40 | 36.83 | 3.43 |
| 6 | 6.63 | 10.57 | 3.93 | | 17 | 36.83 | 41.80 | 4.97 |
| 7 | 10.57 | 19.73 | **9.17** | | 18 | 41.80 | 52.87 | **11.07** |
| 8 | 19.73 | 19.97 | 0.23 | | 19 | 52.87 | 54.07 | 1.20 |
| 9 | 19.97 | 24.90 | 4.93 | | 20 | 54.07 | 54.53 | 0.47 |
| 10 | 24.90 | 26.37 | 1.47 | | 21 | 54.53 | 58.47 | 3.94 |
| 11 | 26.37 | 27.80 | 1.43 | | | | | |

mean **2.78 s**, median **1.47 s**, shortest 0.23 s, longest 11.07 s.
Distribution: six shots under 1 s, six 1–2 s, five 2–4 s, four over 4 s.

**The cuts are not on the music.** 92 onsets detected; the nearest onset to each
of the 20 cut points is a median **95 ms** away and only **7 of 20** are within
60 ms. Three cuts sit 0.75–1.27 s from any onset. The edit is cut to the
picture's own action, with the type carrying the rhythm.

**Freezes.** Three runs where the source is genuinely frozen (frame difference
< 0.35 for 6+ frames): 7.90–8.43, 8.47–9.97, 10.07–10.53 — the Times Square
establishing shot is a still with a slow push, not a moving camera.

## Type — the part that carries the edit

Sampled at 10 fps against a text-free baseline (34–41 s), then measured on the
masked glyphs:

| register | where | size | how long |
|---|---|---|---|
| **stack** | right edge 0.95 W, top 0.094 H | cap **0.110 H**, pitch **0.240 H** | 4 lines max, older lines at 0.34 / 0.58 / 0.78 alpha, newest 1.0 |
| **single** | right edge ≈0.87 W, band 0.75–0.91 H | cap **0.13–0.16 H** | 0.6–1.0 s |
| **bed** | centred, full width | ghost **0.50 H** (alpha 0.40) + solid **0.15 H** | 1.6–2.2 s, always across ≥2 cuts |

- Fill is **silver**, not white: a vertical gradient, cool at the cap line,
  warm at the baseline, with a drop shadow. Against a dark plate flat white
  reads as a subtitle; the gradient reads as an object in the shot.
- Tracking is tight (≈0.018 em) — this face is already wide.
- Colours measured as the densest text pixels: ghost `#7c1119`, solid `#c2131d`.
- The bed is the same phrase repeated, not new copy: LOVE ME appears at 8.4,
  12.9, 20.8 and 29.5 s, i.e. a refrain.
- **The last 6 s have no type at all.** The edit ends on the film.

Type is on screen roughly 55% of the runtime, and it is never the only thing
moving for longer than about four seconds.

## Sound

- Bed sits at **−17 to −19 dBFS** for the whole 58 s. No hits, no impacts, no
  riser at the drop.
- Six **digital-silence** runs (measured at −120 dBFS, not "quiet"):

  | run | length | what it does |
  |---|---|---|
  | 1.75–1.92 | 0.17 | cuts a word out of the intro |
  | 3.52–4.22 | 0.70 | after "FIGHT ME" |
  | 4.96–5.68 | 0.72 | before "OKAY" |
  | 6.10–7.04 | 0.94 | into the bridge shot |
  | **24.10–26.88** | **2.78** | **before the fall** |
  | 29.86–31.05 | 1.19 | before the web-line |

- The return from the long hole measures the **same** level as the bed before it
  (−18.8 dBFS). It reads as enormous because the hole was absolute zero. The
  lift is contrast, not gain.

## Grade

| | whole file | opening 0–6 s | close 52–58 s |
|---|---|---|---|
| mean luma | 41.0 | 46.5 | 31.2 |
| median luma | **31.2** | 35.3 | 19.7 |
| saturation | **0.49** | 0.49 | 0.49 |
| shadow R:G:B | 0.68 : 0.90 : 1.00 | 0.50 : 1.00 : 1.19 | 0.45 : 0.83 : 1.00 |
| pixels > 235 | **0.00%** | 0.00% | 0.00% |

Shadows are teal and heavy; saturation holds at 0.49 while luma falls, so the
picture gets darker without going grey. **Nothing clips.** The brightest thing
in any frame is still information, which is most of why it does not look like a
filter.

## What it implies for the engine

Implemented as `--style reference2`:

1. `studio/ref2type.py` — stack, single, bed; silver fill; the reference's own
   proportions.
2. `studio/ref2.py` — stanza grouping, bed placement, silence-hole placement,
   and the spec in one place.
3. `compose.ref2_grade` — saturation, gamma lift, teal shadows, 235 ceiling.
   A gamma, not an offset: an offset lifts letterbox bars and breaks the
   picture-box detector.
4. `compose.render(style="reference2")` — type registers chosen by card length,
   bed composited behind type, multiple silence windows.
5. `director.segments_for(max_cuts=1)` — one cut per lyric line, so the picture
   can hold while the words move.

Not copied, and why:

- **Dialogue.** There is none in our edits by standing rule.
- **Cutting on action.** We cannot see an actor's intent in a scenepack. Cuts
  hang on the words instead, which is the closest honest equivalent.
- **Vertical reframing.** This reference survives 9:16 because its type lives in
  corner boxes and its picture is wide. Nothing in the system depends on the
  picture being cropped, so a vertical should letterbox and let the type own the
  frame — not slice a band out of the middle (`studio/frame.py`, `VERTICAL_CROP`).
