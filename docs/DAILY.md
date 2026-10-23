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
