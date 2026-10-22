# studio/ — the overedit engine

A second, separate system from the whop campaign chain. Whop cuts speech:
it finds the best 40 seconds of talking and captions it. Studio cuts *music*:
the track is the score and every cut is played against it. They share nothing
but the fonts and ffmpeg, deliberately — a change here can never break a
campaign render.

Format: **1920×1080, 30 fps, 16:9.** Vertical stays with whop.

## The one idea

A fast edit that is fast from the first frame has nowhere to go.

The reference edit (Amazing Spider-Man, 31 s, 1280×720) spends **42% of its
runtime on two shots** — one held 4.5 s, one held 7 s — and then makes **30 shot
changes in the next 16 seconds**, median 0.6 s, shortest 0.23 s. The whole thing
is one long build, a drop, and an exhale, and the build is what makes the drop
read.

So the planner works from an act template, not from a constant cut rate:

| act | fraction | cuts/beat | what happens |
|---|---|---|---|
| build | 0.00–0.42 | 0.11 → 0.55 | holds up to 2.6s, type is the only thing moving |
| drop | 0.42–0.80 | 1.15 | cuts on 8ths and 16ths, flashes on ~1 cut in 5 |
| out | 0.80–1.00 | 0.42 @ 0.55× speed | slow motion, monochrome, release |

Densities are **cuts per beat**, not cuts per second, so a plan retimed to a
different track keeps its shape.

## Pipeline

```
track ──▶ grid.py ──────▶ Grid        BPM, beat-0 phase, sections, onsets
source ─▶ shots.py ─────▶ Source      shot list + motion/sharp/bright/sat per shot
script ─┐
        ├▶ plan.py ──────▶ Plan        which shot, when, how long, which act
        │                    │
        └▶ typecards.py ─────┤
                             ▼
                          compose.py  grade per act, composite type, flash, encode
                             ▼
                           edit.mp4 + .plan.json + .report.json
```

**`grid.py`** — the clock. Two-stage tempo search: a coarse comb over 70–190 BPM,
then a *joint* fine search over tempo and phase. This matters: the coarse winner
was 95.79 BPM on a 96 BPM test track, which is 60 ms of drift across 30 seconds —
enough to see. Phase is taken from a low-band (kick) envelope and corrected for
the attack lag between a transient and its energy peak. Measured error on the
test score: **9.7 ms.**

**`shots.py`** — shot list from frame-difference + histogram change (a whip pan
moves pixels but keeps the palette, so it is not a cut). Streams statistics in
64-frame batches; a 10-minute source is 17k frames, which is 4 GB if you hold it.
Per shot: motion, laplacian sharpness, brightness, saturation, warm/cool/mono.

**`plan.py`** — the editorial brain. Constraints it enforces:
* never the same shot twice in a row;
* prefer shots not yet used, so the edit does not repeat itself;
* a long hold must be a shot *worth* holding — near-black or soft frames are
  penalised only when the hold is long;
* a cut can never be longer than the shot feeding it: if nothing is that long,
  the hold is split into 2–6 cuts on the grid rather than freezing a frame;
* a hold may not exceed `MAX_HOLD_S` (2.6 s in the build and out). Uncapped, the
  only shots long enough to fill a 4.4 s hold in the Spider-Man scenepack are the
  dark atmospheric ones, which forces the edit onto the worst footage in the pack;
* flashes only in the drop, budgeted at 22% of cuts, and only where consecutive
  shots differ hard in brightness or in colour family.

**`typecards.py`** — the words. Sized to the frame (width ≈62%, height ≤26%),
one to three words, tracking between words, drawn **word by word** (per-character
drawing throws away kerning and "MADE" renders as "MAD E"). The accent colour is
per card. On plates brighter than ~90/255 the type gets a blurred-alpha halo —
a shadow that hugs the letterforms, never a grey panel.

**`compose.py`** — per-act grade (contrast, saturation, gamma, shadow tint),
type composite with a 2-frame pop on entry, flash, encode. Sources close to 16:9
are covered; sources far from it (vertical inserts, 4:3 archive) are fitted over
a blurred, darkened copy of themselves — the broadcast answer, which reads as
deliberate where black bars read as a mistake.

## Run it

```bash
# a test score with a real build/drop, so the engine can be checked without a licensed track
python -m studio.synth_score work/studio/test_score.wav

python -m studio.grid work/studio/test_score.wav        # inspect the grid

python -m studio.produce \
  --track work/studio/test_score.wav \
  --source footage/amazing_spiderman.mp4 \
  --script studio/scripts/example.json \
  --start 12.0 --end 40.0 \
  --out work/studio/edit.mp4
```

`studio/scripts/*.json` is the words layer:

```json
{"cards": [{"beat": 0, "text": "They said", "accent": "SAID"}]}
```

Beats are **relative to frame one** (beat 0 = the first frame) and land on the
track's grid, so changing the track moves the words with it.

## The real track and the real footage

`footage/beauty_and_a_beat.mp3` (68.6 s) and `footage/spiderman_scenepack.mp4`
(157 s, 1280×534, Twixtor, graded) are the reference's own ingredients.

Measured: **122.8 BPM, first beat at 0.368 s**, 292 onsets. The sections are
build 0–27.75, build 27.75–41.25, **drop at 41.25**, chorus 48.75–64.24.

Two things that source forced:

* **Tempo.** The envelope comb locked onto **81.9 BPM** — half time — because a
  half-time grid still lands on most of the hits. That is a wrong answer that
  sounds almost right, which is the worst kind. Tempo now comes from an
  onset-comb followed by a musical-range check that resolves half/double, and
  fine phase comes from the kick band because onsets cannot tell a beat from its
  off-beat.
* **Motion.** Every shot in a Twixtor pack measures 0.002–0.019 motion, because
  it is all slow motion. Absolute thresholds made the choice meaningless, so
  shot choice now uses each shot's **percentile rank within its own source**.
* **Hold length.** Only 4 of 17 shots in the scenepack are ≥4.3 s and those are
  the darkest (brightness 29–60, against bright shots at 107 and 79 that are
  short). A 4.4 s hold therefore had exactly one option: something too dark to
  read. Capping holds at 2.6 s widens the choice set — the build now opens on a
  shot at brightness 79 and a close-up at 107.

## Ramps, whips and matte

The three moves the reference used that the first build did not have.

**Speed ramps** (`ramp.py`). A constant-speed shot is the default because it is
easy, not because it is good. On slow-motion footage the single biggest upgrade
is to change speed *inside* the shot so it decelerates into the cut. The ramp is
defined in output time and integrated to a source offset, so `speed(u)` literally
means "seconds of source per second of output" at that moment; its integral is
the mean speed, which is what the planner budgets runway against. Ramps go on
**35% of drop cuts** — every cut ramping is a house style, not an edit.

**Whip transitions** (`compose.whip_frame`). Not a cut with blur on it: two shots
share one or two frames, pushed in opposite directions with a horizontal smear
that peaks mid-transition. Budgeted at 15% of drop cuts, never on the same cut as
a flash.

**Text as matte** (`typecards.composite_matte`). The letterforms become a window
into the plate, showing the same frame magnified 1.7× and pushed in contrast so
the glyph interiors are visibly a different plane. The first version was a pure
matte fill and it failed: over a dark plate the fill inherits the darkness and
the word disappears. The fill is therefore laid over the card's own type at 74%,
so the type holds the shape and the plate gives it the texture — which is what a
compositor actually does, and why it reads on any footage. Matte is reserved for
one card in four in the drop.

## Sound design (`sound.py`)

The picture cuts on the grid, so the sound has to arrive on the same grid. All
SFX are **synthesised** — deterministic, and no licensing question about a hit
you generated yourself.

| cue | where | why |
|---|---|---|
| riser | ends **exactly** on the drop's first frame | one that stops early leaves a hole; one that overshoots steps on the downbeat |
| impact | drop downbeat | the loudest event in the edit |
| whoosh | on a whip, ending on the cut | the picture blur is the other half of the gesture |
| tick | on a flash cut | marks the join without competing with the music |
| swell | first frame of the out act | the exhale needs an entrance |

A sound is only placed where the PICTURE marks a cut (whip, flash, act change) —
not on all 47 cuts. Measured on the render: 15 cues, all within a frame of their
cut, and the impact lifts RMS from 0.211 to 0.288 at the drop.

## Tracking (`track.py`)

Pins a graphic to the subject: Haar finds a face in the first frame of the cut,
pyramidal Lucas-Kanade follows a sparse feature set inside a grown face box, and
a short median filter removes the per-frame jitter that reads as a bug. A card
with `"pin": true` in the script follows that point instead of sitting centred,
and is clamped so it can never leave the frame.

Tracking is measured, not assumed: 0 lost frames over 30-frame cuts on this
footage (subway pan 248 px, close-up 78 px). LK drifts over a long hold, so it is
only used on drop-length cuts; where no face is found the card stays centred.

## What is not built yet## Verification

`python -m pytest tests/test_studio.py` runs without ffmpeg-heavy renders:
grid phase accuracy, plan structure invariants (no freeze, act ratios, flash
budget), and card metrics.
