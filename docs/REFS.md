# What the reference edits actually do

Measured off the files frame by frame. Every number below comes from decoding
**every frame** at native size and comparing consecutive frames — not from
sampling a few thumbnails and calling it a study.

## The four reels

| | 1000106089 | 1000107167 | 1000110841 | 1000113144 |
|---|---|---|---|---|
| length | 17.87 s | 12.33 s | 30.05 s | 27.60 s |
| native rate | 60 fps | 60 fps | 60 fps | 60 fps |
| cuts | 14 | 13 | 46 | 26 |
| cuts / sec | 0.78 | 1.05 | **1.53** | 0.94 |
| shot median | 0.60 s | 0.83 s | **0.17 s** | **0.13 s** |
| shot mean | 1.19 s | 0.88 s | 0.64 s | 1.02 s |
| longest shot | 3.40 s | 3.00 s | 3.83 s | **13.67 s** |
| full-frame cards | 5% | 26% | 0% | 3% |

## Three things that fall out of that table

**1. Median and mean disagree, and that is the whole style.** `1000110841` has a
median shot of **0.17 s** — ten frames — but a mean of 0.64 s and a longest shot
of 3.83 s. `1000113144` is starker: median 0.13 s, longest 13.67 s. A reel does
not cut at one speed. It fires a **burst of five-to-eight-frame cuts, then holds**
on one image for one to three seconds. The hold is what makes the burst read as
aggression instead of noise.

**2. They do not cut on the beat.** Measured against each reel's own tempo:

| | detected BPM | median distance cut→beat | cuts within 40 ms of a beat |
|---|---|---|---|
| 1000106089 | 55.0 | 221 ms | 0% |
| 1000107167 | 78.2 | 229 ms | 23% |
| 1000110841 | 126.8 | 126 ms | 17% |
| 1000113144 | 112.5 | 100 ms | 8% |

If these were beat-cut, that median would be under 20 ms. It is 100–229 ms,
which is a quarter to a half of a beat — the signature of cutting to **speech**,
where the cut lands on the syllable, not the kick drum.

This matters because the whole house engine cuts on a musical grid. On a
voice-over reel that is wrong, and it is why a beat-perfect cut can still feel
dead: it is on time and off the words.

**3. The text is a cut, not a caption.** Where the reels use type, it replaces
the picture — 26% of `1000107167` is full-frame cards, in runs of 0.23 s to
3.0 s. Type is not laid over a shot and left to sit; the shot ends, the card is
the shot, the shot comes back.

## What this means for a music edit

The Gothic part and the practical part are worth separating.

- **Portable:** the burst-then-hold rhythm. Micro-cuts as accents, long holds
  between them. This is true of every reel here and it is true of good music
  edits as well.
- **Not portable:** cutting to speech instead of the beat. Arcade has no voice
  in the window we use, so the grid is correct for this job.
- **Not portable:** full-frame cards replacing the subject. On a death scene the
  face *is* the scene; a card over it throws away the only thing that carries
  feeling. Cards stay as fragments under the picture for `cold_read`.

## Applied to `post3`

`footage/post3/cutmap.json` is now 53 cuts: **21 micro-cuts** of 4–8 frames and
**10 holds** of 1.5 s or more, with the slow-motion holds carrying the emotional
beats. Ending moved onto Peter holding her, which is the shot the scene is about.

## What is missing

The cinematic Gwen-type references are **not in this sandbox**. There is no
music-led edit anywhere in the repo to measure against — the only edit-like
material is the four reels above plus Premiere/AE tutorials whose frame
differences are screen-capture UI changes, not cuts. Anything claimed about that
style would be invented, so none of it is claimed here.

---

# The tutorials, transcribed

The four reels show *what* the edits look like. The tutorials show *how they are
made*, so I transcribed the time-remap one rather than inferring it from
thumbnails (ASR runs in CI; the audio slice is `work/ref_remap.mp3`).

What he actually says, verbatim:

> "you want to press ctrl-alt-T … and you see this timer map opens"
> "if you listen to a song on marker 2 the B will start"
> "pressing I will go to the start and pressing O will go to the end"
> "press F9 or right click and go keyframe assistant and go Easy Ease"
> "since this is the start, I want this to be starting slow. If I do this it'll
>  be very fast; if I do this it will start slow, and I want to do it towards
>  the middle, not straight up"
> "there's 80 at the top and zero, so under 40"

## The method, in three rules

1. **Time remap, not slow motion.** The speed is a *curve* over the clip, not a
   constant. He opens the speed graph and drags the handles.
2. **Easy Ease every keyframe (F9).** Both edges are flat. The change of pace is
   approached smoothly from a normal-speed moment, never stepped into.
3. **Never let the curve hit zero or go vertical.** "Towards the middle, not
   straight up." A speed of zero is a freeze; a vertical jump is a snap. He
   works in the middle of the graph on purpose.

Plus two timing habits: clips are laid on **music markers**, and cuts are made
against the **action** ("this is where he shoots", "right before you open the
scoreboard" — i.e. cut *before* the beat you want to hide).

## What that changed in the engine

`studio/ramp.py` gained eased ramps — `sink` (normal → slow) and `surface`
(slow → normal) — which use a smoothstep edge instead of a power curve, the
software equivalent of F9. Eleven cuts in `footage/post3/cutmap.json` now use
`sink` instead of one flat speed.

Measured on the render: inside the ramped section (41.0–45.4 s) the
frame-to-frame difference never reaches zero — **minimum 0.75, median 2.98, no
dead frames**. The picture keeps moving through the whole slow-motion passage,
which is the entire point of the rule.
