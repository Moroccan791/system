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

---

# Frame-accurate pass (second study)

The first pass sampled at 2 fps and missed things. This one read every one of
the 1,750 frames at 30 fps, classified each transition as a cut / a dissolve /
a blur-whip, measured motion inside every shot, isolated the kick band (35–120
Hz) and the cymbal band (6–10 kHz), and pulled single frames around every event.
Corrections and new findings:

## Structure, corrected

**24 hard cuts, not 21.** The earlier count merged three pairs that are real
0.2–0.4 s cuts. Shot lengths: min 0.17 s, median 1.27 s, mean 2.37 s, max 11.90 s.

The distribution is violently uneven on purpose:

| | cuts | what happens |
|---|---|---|
| 0.00–10.6 | 6 | establishing, dialogue, the stack of four lines |
| 10.6–19.7 | **0** | **one shot held 9.17 s** — the ceiling hole, the fall begins |
| 19.7–19.97 | **4 in 0.27 s** | the fireball |
| 19.97–24.9 | 1 | the explosion, held 4.9 s |
| 24.9–33.4 | 8 | the fall, accelerating |
| 33.4–36.8 | 1 | the lens, held 3.4 s |
| 36.8–41.8 | 0 | held 5.0 s |
| 41.8–52.8 | **0** | **held 11.06 s** — the catch |
| 52.8–58.3 | 6 in 5.5 s | the end, intercut with the web |

## The four-frame event at 19.73–19.93

The most deliberate thing in the edit. Frame by frame:

    19.70  Spider-Man's back, over the gantry
    19.73  fireball fills the frame (orange)
    19.77  fireball, brighter
    19.80  whiteout begins — luma 228 (local median 105)
    19.83  whiteout, luma 245
    19.87  whiteout, luma 245
    19.90  whiteout, luma 242
    19.93  whiteout, luma 232
    19.97  the gears, blown orange, from underneath

Four hard cuts in 0.27 s, then five frames of near-white, then the wide. The
white is not a flash ON a cut — it is the cut. Also note the 0.75 s before it:
the music is already falling (18.0 −33 dB, 18.5 −39, 19.0 −42) so the whiteout
lands where the track has gone thin.

## The blur-whiplash at 12.0–13.7

Frame differencing shows 40–60 consecutive frames at diff 18–28 with no single
peak and no still frame between them: the picture is in continuous motion, not
cutting. It is a speed-warp/zoom-blur burst — the shutter, not the edit. Our
engine can approximate it with a strong ramp inside one long shot; it cannot
reproduce it with cuts.

## The lens reveal at 35.0–36.8 (3.4 s, one shot)

A slow push into Spider-Man's mask until the right lens fills a third of the
frame, and the web pattern inside the lens becomes a portal: at 35.0 it is
texture, at 35.8 a blurred kiss starts to resolve inside it, by 36.6 the kiss
is sharp inside the lens while the mask stays sharp around it. This is a masked
composite with a fade-in, tracked to a curved surface. It is the single most
expensive-looking shot in the reference and it is the one no template copies
without a mask and a tracker.

## Motion inside the shots

Classified by comparing first-half to second-half motion:

- accelerating (ramp in): 19.93, 28.23, 29.13, 52.83, 54.50 — the action beats
- decelerating / slow-mo: 5.90, 33.37, 36.80
- near-still, push only: 30.97–33.37
- the two long holds are *steady*, not frozen: the camera moves the whole 11 s

Two genuine freezes only: 9.63–9.97 and 10.07–10.53, inside the Times Square
establishing shot.

## Cuts vs kicks, corrected

54 kicks detected in the whole file and they are not spread evenly: the first
kick is at **7.58 s**, and 29 of the 54 fall after 34 s where the track turns
into 16ths (median interval 0.16 s).

| cuts | on a kick (<80 ms) |
|---|---|
| before 33 s (18 cuts) | **1 / 18** |
| after 33 s (6 cuts) | 2 / 6 |

So: the edit is cut on the action for the first two thirds and starts cutting
near the kick grid only in the last third. "Every transition is on a downbeat"
is not what this file does, and building that way would produce a different,
busier video.

## Sound, corrected

The RMS table (0.25 s windows) shows the "bed at −17 to −19 dBFS throughout"
claim is only true after 31 s. Before that the level is *moving*: drops to
−120 dBFS at 5.0, 6.5, 24.5–26.9, 30.0–31.0, and falls to −33/−39/−42 dBFS
going into the whiteout at 19.8. The silences are not just holes punched in a
flat bed — the whole first half is being ducked and slammed.

## Text inventory (what is actually on screen)

| t | text | register |
|---|---|---|
| 0.0–2.9 | YOU / AND ME / YOU WANNA / FIGHT ME | stack, right, 4 lines, silver |
| 3.2 | GO | single, low centre-right |
| 4.9 | OKAY | single, red |
| 8.4–10.0, 12.9–14.6, 20.8–22.4, 27.5–29.1 | LOVE ME | bed: huge crimson ghost + solid small |
| 16.0 | YOU | stack, single line |
| 34.0 | OH BABY | bed (red, two lines of scale) |
| scattered | YOU / ME / ALL I NEED / I SAVE HER … | single, low right, 0.4–1.0 s |

Text is present in roughly 55% of the runtime and **absent for the final 2.2 s**.
