# Reference decomposition — "✨ #spiderman" (Amazing Spider-Man overedit)

Source file: `✨ #spiderman #spidermanedit #trending #viral #fyp.mp4`
31.27 s · 1280×720 · 30 fps · H.264 · AAC
Watermark `SYRIS`, bottom left, for the full duration. No end card, no CTA.

Everything below was measured from the file (frame differencing, histogram
change, spectral-flux onset detection, per-frame laplacian variance), not
eyeballed. Where a number is an estimate it is labelled as one.

## Structure

| section | time | shot changes | level | what carries it |
|---|---|---|---|---|
| build | 0.0–13.0 | **2** | −16 to −19 dB | type alone over near-static shots |
| ramp | 13.0–14.6 | 4 | rising | acceleration into the drop |
| drop | 14.6–25.3 | **21** | −10 dB | cuts, type, grade, flashes |
| exhale | 25.7–30.5 | 5 | falling | slow motion, monochrome memory |
| out | 30.5–31.3 | — | — | fade to black |

**45% of the runtime contains almost no cutting.** Two shot changes in the first
11.5 s: one close-up held ≈4.5 s, then a two-shot held ≈7 s. The next 16 s
contains 30 changes.

## Cutting

- median shot **0.60 s**, shortest **0.23 s** (7 frames), longest 1.37 s in the drop
- intervals inside the drop: 1.17, 1.23, 0.73, 0.43, 0.23, 0.23, 0.70, 0.67 …
- onset spacing across the track: median **0.174 s** → 16th notes at **≈94 BPM**
- cuts cluster on the 16th grid, e.g. 15.03 / 15.27 (7 frames), 21.13 / 21.37 /
  21.77, 24.60 / 24.83 / 25.07

## Sound

- build −16 to −19 dB, drop −10 dB: a **6–8 dB step** at ≈14.0 s
- **no silence anywhere** in the file; the drop is loud because the build is quiet
- 93 detected onsets; the riser occupies the last bar before the downbeat

## Transitions

The largest frame-to-frame jumps come in **pairs** 1–2 frames apart
(13.87/13.90, 16.87/16.90, 22.93/22.97, 23.90/23.93). Two enormous changes one
frame apart is not a cut — it is a flash or a double-sided transition. This is
the one transition primitive worth copying exactly.

## Type

- centred, all caps, tight leading, tracking open, **1–3 words per card**
- card height ≈15–20% of frame height
- text is the **vocal lyric**, karaoke-style, not the dialogue:
  `LOST / GWEN / MY… / I / SAVE / HER / ALL / I NEED / IS A / BEAUTY / AND A /
  BEAT / WHO CAN / MAKE / MY / LIFE`
- during the drop the cards change every 0.23–0.40 s, i.e. with the 16th grid
- on the lens close-up (18.4 s) the letterforms are **filled with the plate
  underneath** — text as matte, not flat white type

## Grade

- median luma **36/255**, floor 16 — crushed and contrasty
- amber halation on window light; chromatic aberration on the scaffold shot
- **12% of frames are motion-blurred** (whip pans, speed ramps)
- colour changes by act: cold near-mono (grief) → hot teal/red (drop) →
  full monochrome at 25.7 s (memory) → warm golden skyline (resolution)

## What this implies for the engine

Implemented: act template with a sparse build; cuts on the beat grid;
type sized to frame with 1–3 words; per-act grade; flash transitions budgeted;
slow motion in the out act.

Not yet implemented, in value order:
1. text-as-matte (the most distinctive single move in the reference)
2. double-sided 1-frame transitions
3. beat-locked sound design (hits/risers on the grid)
4. speed ramps mid-shot
5. optical-flow / point tracking for pinned graphics
