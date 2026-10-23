# The daily loop

One video a day: raw footage + the audio in, a finished 1920×1080 edit out, with
the handle burned in and the listing written by the same run. This file is the
whole process — if a step is not here, it did not happen.

## What comes in

| what | from | where it goes |
|---|---|---|
| raw footage (scenepack) | you, as a file or a release asset | `footage/<name>/raw.mp4` |
| the audio to cut to | you | `footage/<name>/track.mp3` |
| the lyric, timed | you send the words, the times get placed | `studio/lyrics/<name>.timed.txt` |
| who/what it is about | you tell me, I research the fandom | `studio/briefs/<name>.json` |

If the files are over ~20 MB they arrive as a GitHub release asset and are
pulled in by the repo's own bridge — `.github/footage-request.json` plus a push,
then `git pull`. No uploads into chat, no re-sending what is already on `main`.

## The command

```bash
python -m studio.pipeline \
  --video footage/<name>/raw.mp4 \
  --audio footage/<name>/track.mp3 \
  --timed studio/lyrics/<name>.timed.txt \
  --brief <name> \
  --font <face> \
  --start <s> \
  --out studio/out/<name>.mp4
```

Three ways to give it the words; pick by what the mix does, not by habit:

- `--timed` — each sung line carries its own time. **The default for edit
  audio.** A 128 kbps YouTube edit has the vocal buried; the recogniser both
  mishears words and spreads its anchors unevenly, which produced cards that
  overlapped by half a second.
- `--captions` — plain lyric, the recogniser places it. Only when the vocal is
  exposed (an album master, a slow section).
- `--cards` — a table already placed and approved. Rebuilds nothing.

`--font` is required and stops the run without it: the face is your choice, and
a render that quietly picks one is a render nobody chose.

`--dry-run` stops after the card sheet and the plan — the approval step before
six minutes of encoding.

## What comes out

Next to `--out`:

| file | what it is |
|---|---|
| `<name>.mp4` | the video — 1920×1080, 30 fps, stereo, handle on every frame |
| `<name>.post.md` | **the upload screen**: titles, caption to paste, hashtags |
| `<name>.cards.jpg` | one tile per caption card, for approval |
| `<name>.script.json` | the card table the render used |
| `<name>.gate.txt` | the ship gate's verdict |
| `<name>.sync.txt` | every card checked against the audio it sits on |

## The gate — what "ready" means

`studio.gate` measures the finished file, because every miss this project has
had was a property of the encode that nobody checked:

```
PASS  resolution       1920x1080
PASS  frame rate       30.00 fps
PASS  audio            2 channel(s)      <- the mix keeps its stereo image
PASS  no dead frames   0 frame(s) below luma 12
PASS  handle           brightness +70 over its surround
PASS  captions fit     last card 41.96s vs 42.60s of picture
      READY TO POST
```

It runs automatically at the end of the pipeline. `DO NOT POST` means it does
not ship — and the reason is printed there, not discovered on a phone.

## The listing

Never written from memory at upload time. `studio.publish` builds it from the
brief: the hook is a sentence a viewer would repeat, the titles are three
variants under the platform limits, the tags are searchable ones from the
fandom. It is written **before** the render so it can be reviewed next to the
card sheet.

A video cannot be cut without a brief. `--brief` unknown stops the run and lists
what exists.

## Adding a video

1. `studio/briefs/<name>.json` — the research, in this shape:

```json
{
 "title": "Peter Parker — Brand New Day · Stay",
 "topic": "Spider-Man: Brand New Day (2026), Tom Holland / Zendaya",
 "thesis": "one sentence: what this edit IS",
 "song": "Stay — The Kid LAROI & Justin Bieber (edit audio)",
 "tags": ["spiderman", "tomholland", "brandnewday"],
 "hooks": ["he chose to be alone", "brand new day, same gravity"],
 "audience": [{"claim": "what the fandom actually responds to", "source": "where it was observed"}],
 "lyric": [{"line": "a sung line", "needs": "two_shot", "why": "what the shot must do"}],
 "avoid": ["shots that would break it"]
}
```

2. `studio/lyrics/<name>.timed.txt` — one sung line per line:

```
[00:10.290 - 00:13.450] I'll be fucked up if you can't be right here
[00:13.600 - 00:16.400] I do the same thing I told you that I never would
```

Both times optional; a start alone runs to the next line. **Every sung line
needs its own entry** — a missing repeat shifts every caption after it, which is
exactly the bug that made the last chorus read a line early.

3. `studio/director.py` — `LINE_DIRECTION_<name>`: which shots answer which
line, in order, six deep per line so no shot returns inside a second.

## Fixed decisions, so they are not re-litigated per video

- **1920×1080, horizontal only.** Vertical was dropped.
- **The handle is `@fayzann.edits`**, bottom centre, plain DejaVu Sans, 62%
  white with a hairline shadow — never one of the edit faces. It comes from
  `assets/fonts/family.json`, so it is on by default and everywhere.
- **Stereo.** The analysis works on one channel; the mix never does.
- **Grading is the studio's call**, premium and not obviously filtered.
- **Length follows the vocal**, not a target: the edit ends 1.2 s after the last
  placed word, and refuses an `--end` that would cut a line.

## The handle goes on the picture

Scenepacks are often a 16:9 file with the film's own 2.05:1 image letterboxed
inside it, and those black bands are baked into the footage — the renderer did
not add them. Positioning the handle a margin from the frame's bottom edge puts
it *in the band*: a white handle floating on black, under the picture, which
reads as a caption on the canvas rather than a credit on the edit.

So the picture box is measured from the pixels once per source
(`watermark.rect_from_video`, sampling nine frames and taking the median row and
column profile), and the handle is placed inside that box, a fixed fraction
above its bottom edge. The gate looks for it there, falls back to the old frame
position so an already-shipped file still verifies, and prints which one it
found.

## Formats, behaviours, and the five tools built for them

**Shape** is `--format landscape|vertical|square`. Vertical is 1080x1920, the
picture is cropped or padded to fill it, and type is placed inside the platform
safe area (top 10%, bottom 22%) rather than centred on the canvas — the caption
block on Reels/TikTok/Shorts draws over the bottom fifth, so type there is
invisible. A 2.35:1 picture is padded over its own blurred enlargement rather
than cropped to a middle third.

**Behaviour** is `--behaviour lyric|crescendo|mosaic` — how the picture cuts:

| | cuts | use it for |
|---|---|---|
| `lyric` | one image per card, held | the default; the type leads |
| `crescendo` | nothing moves until the first word, then one cut per word | proving confidence; the stillness is the format |
| `mosaic` | one image per word, no holds | fast tracks; pair with `words.explode` |

**Silence** is `--silence-before-drop MS`: the score is cut dead for that long
before the drop, with 6ms edges. It measures as digital zero against −15 dBFS
when the drop lands. This is the "cold open" that needs no dialogue.

**Sound design** is `--design tape_stop`: the music stops itself into the drop
instead of a riser, plus a sub on the downbeat. Registered beside impact,
whoosh, riser, tick and swell.

**Loops** — `studio.loop.find(pack, shots)` ranks shots by whether they close on
themselves (end-vs-start pixel distance against mid-vs-start). It reports; it
cannot manufacture a loop. A pack with no closing shot simply is not a loop edit.

**Two songs** — `studio.twosong build --a quiet.mp3 --b loud.mp3 --a-secs 20
--b-secs 40` writes one bed and returns the join. Render that bed normally and
put the direction sheet's turn on the join.

## Reference 2: the system behind "Gwen Stacy's death" (58.5 s, 3.7M likes)

Reference 1 is what this house already does: the lyric as a centred card that
changes with the vocal, cuts on the music grid. Reference 2 is a different
machine, and it is measurable rather than a vibe. Decomposed frame by frame
(scene-cut detection, 10 fps type masks, digital-silence runs, 2 fps grade
statistics) — the full numbers are in `studio/reference/gwen_death.md`.

**It is not a beat edit.** 21 shots in 58.5 s: mean 2.78 s, median 1.47 s, with
one shot held 11.07 s. Only 7 of its 20 cut points sit within 60 ms of an audio
onset. Copying it by cutting faster is copying it backwards.

What makes it feel expensive:

| | what it is | in the engine |
|---|---|---|
| **the stack** | a right-aligned block of lyric lines that ACCUMULATES, newest bright, older lines at 0.34/0.58/0.78, four deep, then a fresh stanza | `studio/ref2type.py: stack_face`, `ref2.stacks/stack_at` |
| **the silver fill** | a vertical gradient, cool at the cap line, warm at the baseline, plus a drop shadow — flat white reads as a subtitle | `ref2type._fill`, `SILVER` |
| **the bed** | one phrase set enormous in crimson BEHIND the subject, cropped at the frame edge, repeating every few seconds across cuts | `ref2type.bed`, `ref2.beds` |
| **the single word** | one line, low right, when the picture is doing the talking | `ref2type.single` |
| **the silence holes** | digital zero — 0.70 s, 0.95 s, then 2.78 s ending exactly on the biggest move | `ref2.holes`, `compose._sound(gaps=)` |
| **the grade** | median luma 31/255, saturation 0.49, teal shadows, and **nothing above 235** | `compose.ref2_grade` |
| **the long hold** | one cut per lyric line, so a shot can sit for 2.6 s while the type moves | `director.segments_for(max_cuts=1)` |

One command:

```
python -m studio.pipeline --video pack.mp4 --audio song.mp3 \
  --cards studio/out/<edit>.cards.json --brief <brief> --font <face> \
  --style reference2 --bed "<the phrase>" --accent-at <hit in edit time> \
  --out studio/out/<edit>_ref2.mp4
```

`--style reference2` also switches the behaviour to `lyric` unless told
otherwise: the per-word behaviours belong to reference 1, and a reference 2 edit
that cuts on every word is neither system.

## Two bugs this pass earned

**The handle measured 0 on a bright render.** The gate looks for the handle at
the position the renderer computed, and the renderer was computing it from the
SOURCE file's picture box (0,140,1860,930) while writing a frame with no bars at
all. Two fixes: `compose._out_box` derives the box from the OUTPUT layout, and
`watermark.rect_from_video` snaps a full-frame box to the frame, because the
192x108 sampler returns 1910x1070 for a picture that fills the frame and a
ten-pixel error moves the mark ten pixels.

**A render "finished" with no video in it.** The encoder's exit code was read
and discarded; x264 had died and the job went on to mux a file that did not
exist. `compose.render` now raises with the encoder's last 800 characters rather
than continuing.

**The stack silently collapsed to one line.** `ScriptCard` has no `start` field —
its time is `beat` and its length is `until` in beats — so the stanza grouping
measured every card from 0.0, saw an enormous gap before each one, and broke the
block into single lines. The compositor now builds plain `{start, end, text}`
rows before grouping. Anything that reads card timings must accept both shapes.
