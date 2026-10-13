# clipper

Turn a creator's long-form footage into vertical 9:16 clips that match the style
of the reference clips they approved — captioned, styled and export-ready for
TikTok, Instagram Reels and YouTube Shorts.

Built for [Whop](https://whop.com) clipping campaigns, where a campaign folder
looks exactly like this:

```
campaigns/<name>/
├── references/     example clips the creator approved   (style ground truth)
└── raw/            the creator's long-form footage      (what we cut)
```

Everything runs locally, offline, with free/open-source tools (Python + FFmpeg).

---

## Status

| # | Stage | State |
|---|-------|-------|
| 0 | `scan` — probe a campaign into `work/<name>/manifest.json` | done |
| 1 | `style` — learn the style from `/references` → `styles/<name>.style.json` | **done** |
| 2 | `select` — find the moments worth clipping in raw → `work/<name>/candidates/` | **done** |
| 3 | `captions` — word-level ASR, styled captions, 9:16 burn-in | **done** |
| 4 | `edit` — cut the chosen moments to the profile's rhythm and camera | **done** |
| 5 | `export` — platform presets | planned (presets exist, used by stage 3 already) |

`FEATURES.md` is the menu: everything that exists, and everything that could be
added next, numbered so you can just ask for *"C2 and V4"*.

---

## Install

```bash
pip install -r requirements.txt
```

FFmpeg: the wrapper finds it in this order —
`$CLIPPER_FFMPEG` → `ffmpeg` on `PATH` → the static build inside the
`imageio-ffmpeg` wheel. **Captions need a build with libass** (`subtitles`
filter). On Windows grab a full build (e.g. gyan.dev) and put it on `PATH`.

Check everything:

```bash
python -m clipper doctor
```

---

## Quick start

```bash
# 1. see what the tools can do, and generate a synthetic campaign to play with
python -m clipper doctor
python -m clipper samples
python -m clipper scan
python -m clipper style campaign_demo      # learn the campaign style
python -m clipper select campaign_demo     # find the moments worth clipping
python -m clipper edit campaign_demo       # cut and zoom them into 9:16 clips

# 2. open the workspace viewer (watch footage, styles and results)
python -m clipper serve            # http://localhost:8000

# 3. captions on a real clip (real speech recognition, no API keys)
python -m clipper captions campaigns/mycampaign/raw/episode.mp4 \
    --campaign mycampaign --platform tiktok
```

Output lands in `output/<name>.captioned.mp4`, intermediates in `work/<name>/`.

---

## Stage 1 — style extraction (ready)

Point it at a campaign folder; it watches the approved reference clips and
writes the profile that every later stage obeys.

```bash
python -m clipper samples              # if you have not generated the demo yet
python -m clipper style campaign_demo  # → styles/campaign_demo.style.json
python -m clipper style                # every campaign found
python -m clipper style mycampaign --fps 8 --width 640 --max-seconds 30
```

It prints a summary and writes two things:

| File | Purpose |
|------|---------|
| `styles/<campaign>.style.json` | the profile (hand-editable, see `## The style profile`) |
| `work/<campaign>/style/report.json` | per-reference measurements + evidence frames |

### What it measures, and how

| Signal | Method | Typical accuracy |
|--------|--------|------------------|
| Cut points / shot length | frame-difference + content-aware shot boundary detection | exact on the test clips (2.0 s shots read 2.0 s) |
| Zoom / punch-in | multi-scale normalised cross-correlation against the shot's first frame | ±0.02 on scale, ±0.05 s on duration |
| Caption position | glyph band tracking over time, median centre | ±0.01 of frame width/height |
| Caption size | glyph cap-height → ASS size, calibrated against this renderer at run time | ±5 % on normal footage |
| Caption colours | 16-bin palette of the glyph pixels, base vs karaoke highlight split by semantics | exact within JPEG/H.264 noise |
| Casing | row-ink profile (capitals are top-heavy, lowercase ink sits mid-glyph) | correct on all test clips |
| Karaoke | does the accent colour appear mid-cue and spread as words are spoken | correct on all test clips |
| Words per cue / max chars | word blobs and character widths per cue | ±1 word |
| Loudness, music bed | EBU R128 via ffmpeg, tonal-energy-vs-speech-gap heuristic | loudness exact, music bed heuristic (reports confidence) |

`font_family` is the one thing pixels cannot tell you, so it stays `null` and a
note is added to the profile: set it by hand if the campaign uses a specific
face. Everything else is measured.

### Honest limits

* Font size is derived from cap height, which depends on the face. The profile
  carries `font_size_uncertainty` (about ±30 %) and a note explaining it: the
  number is right for Montserrat (the renderer default) and off by that margin
  if the campaign uses a much taller/wider face. Set it by hand if you know it.
* Lowercase captions measure x-height, which reads about a fifth small: the
  uncertainty is widened when `casing` is `null`.
* Caption reading needs text that is visible to a human. Captions that only
  appear for a frame or two, or that are half-hidden behind a busy texture,
  produce low `confidence` rather than a confident wrong answer — check
  `work/<campaign>/style/evidence/*.png`, which are annotated frames of what the
  extractor actually saw.

---

## Stage 2 — moment selection (ready)

Finds the parts of a long recording that are worth cutting out, and says why.

```bash
python -m clipper select campaign_demo                 # every raw file in the campaign
python -m clipper select campaign_demo --top 8          # more candidates
python -m clipper select campaign_demo --min 20 --max 60
python -m clipper select raw/episode.mp4 --transcript work/episode/transcript.json
```

Options: `--platform` (sets the target clip length: tiktok 15-45 s, reels/shorts
15-60 s), `--min` / `--max` to override it, `--top` per file, `--transcript` to
point at a `transcript.json` (stage 3 writes them; the campaign folder, a
sidecar `<file>.transcript.json`, and `work/<file>/transcript.json` are found
automatically).

Output: `work/<campaign>/candidates/<file>.json` plus a readable
`<file>.report.md`, and the same moments appear as **seekable players** in the
workspace viewer (`python -m clipper serve`), so you can skim what it picked
before committing to an edit.

### How it decides

```
audio ──▶ RMS envelope ──▶ loud stretches            ┐
transcript ──▶ sentences ──▶ hook score              ├──▶ grow into clip-sized
                              (questions, numbers,   │    windows, one moment
                               stakes, contradiction)│    each, snapped to pauses
```

* **Loud stretches** are relative to the clip's own baseline, not a fixed
  threshold, so this works on both quiet and loud recordings. Bursts separated
  by short gaps (a laugh, applause) are merged into one moment.
* **Hook scoring** is a small, readable rule set: questions, statistics, money,
  list promises ("three reasons…"), contrarian claims ("nobody tells you"),
  stakes ("I lost…"), emotion words, second-person address. Filler ("you know",
  "kind of", "I mean") is penalised. Every rule that fires is reported as a
  reason, so the output can be checked line by line.
* **Growing a window** starts from the best sentence (or the loudest stretch
  when there is no transcript) and walks outwards until the clip is long enough.
  Two rules keep it honest: a window never swallows a *different* moment, and two
  moments a few seconds apart produce two clips - the weaker one is trimmed
  towards its own moment rather than thrown away.
* **Edges snap to pauses** so a clip does not start or end mid-word.

### Honest limits

* With no transcript this is audio-only: it finds reactions and loud moments,
  but it cannot tell a punchline from a cough. Run stage 3 first
  (`python -m clipper transcribe FILE`) and pass the transcript for the text
  path.
* Hook detection reads *wording*, not meaning: a sentence that is interesting but
  plainly worded scores low. It is a ranking aid, not an editor.
* The demo episode in `samples/campaign_demo/raw/` exists so you can check it
  without real footage: loud stretches at 7.0-12.5 s, 20.5-26.5 s and 33.0-38.0 s,
  with a scripted transcript that puts a hook inside each one. The extractor
  finds all three, with and without the transcript.

---

## Stage 3 — captions (ready)

```bash
python -m clipper captions RAW.mp4 [options]
```

| Option | Default | What it does |
|--------|---------|--------------|
| `--campaign NAME` | — | use `styles/NAME.style.json` if it exists |
| `--style PATH` | — | use a specific style profile JSON |
| `--platform` | `tiktok` | `tiktok` \| `reels` \| `shorts` (resolution, bitrate, loudness target) |
| `--asr` | `auto` | `moonshine` (default) \| `faster_whisper` \| `fixture` |
| `--model` | `small` | whisper model size when `--asr faster_whisper` |
| `--fit` | `cover` | `cover` (centre crop) \| `blurpad` (blurred background) \| `none` (letterbox) |
| `--max-words` | from style | words per caption cue |
| `--mode` | `line` | `line` (karaoke fill) \| `word` (one highlight per word) |
| `--ass-only` | off | write the `.ass` and skip encoding (fast iteration) |
| `--out PATH` | `output/<name>.captioned.mp4` | where to write the video |

Exactly what happens:

```
video ──decode audio 16 kHz──▶ ASR ──▶ word timings ──▶ cues ──▶ .ass ──▶ 1080x1920 mp4
                                        │                │        │
                             native, or energy     2-4 words   style profile
                             alignment if missing  sentence    (font, colour,
                                                   aware       karaoke, position)
```

Artifacts written to `work/<name>/`: `transcript.json`, `cues.json`,
`captions.ass`, `style.used.json`, `report.json`.

### Speech recognition, honestly

| Provider | Install | Word timings | Notes |
|----------|---------|--------------|-------|
| `moonshine` | `pip install moonshine-cpp` | estimated (energy aligner, ±~100 ms) | **default**; real ONNX weights ship inside the wheel, so it works with zero downloads |
| `faster_whisper` | `pip install faster-whisper` | exact | best quality; `--model small` is a good CPU choice, `medium` if you have cores to spare |
| `fixture` | built in | exact (supplied) | tests and dry runs |

`--asr auto` prefers faster-whisper when it is installed, otherwise moonshine.
Moonshine is fully offline and fast (~5× realtime on 2 CPU cores); its timings
come from the energy aligner described in `clipper/align/energy_align.py`.

### Trying real speech without a real podcast

```bash
python -m clipper transcribe samples/campaign_demo/raw/raw_01.mp4
```
(the synthetic sample is a tone, not speech — real ASR needs real audio; drop a
real file in `campaigns/<name>/raw/`)

---

## Stage 4 — edit assembly (ready)

Turns the moments stage 2 picked into finished 9:16 cuts whose rhythm and camera
work come from the style profile.

```bash
python -m clipper edit campaign_demo                    # every raw file, top candidate
python -m clipper edit campaign_demo --top 3 --platform reels
python -m clipper edit campaign_demo --ids "#01,#03"     # only these candidates
python -m clipper edit campaign_demo --shot-len 1.4      # override the profile's pacing
python -m clipper edit campaign_demo --transition fade        # crossfade between shots
python -m clipper edit campaign_demo --transition fade_black  # dip through black
python -m clipper edit campaign_demo --transition circleopen  # any of ffmpeg's 58 blends
python -m clipper edit campaign_demo --focus top         # bias the 9:16 crop upwards
python -m clipper edit campaign_demo --plan-only         # write plans, encode nothing
```

| Option | Default | What it does |
|--------|---------|--------------|
| `--top N` | `1` | how many candidates per raw file to assemble |
| `--ids "#01,#02"` | all of `--top` | assemble exactly these candidate ids |
| `--shot-len SECONDS` | from style (`pacing.avg_shot_len`) | average length of a shot |
| `--platform` | `tiktok` | `tiktok` \| `reels` \| `shorts` (1080x1920, crf, bitrate) |
| `--focus` | `centre` | `centre` \| `top` \| `bottom` — which part of the frame the 9:16 crop keeps |
| `--transition NAME` | from style | `cut` \| `fade` \| `fade_black` \| `fade_white` \| any `xfade` blend (`wipeleft`, `circleopen`, `zoomin`, …) |
| `--transition-duration SECONDS` | from style (0.25) | how long a blend lasts |
| `--tag NAME` | auto | suffix for the output name, so a fade and a cut version can sit side by side |
| `--style PATH` | campaign profile or defaults | style profile JSON |
| `--transcript PATH` | found automatically | transcript used for pause snapping |
| `--plan-only` | off | write the plan JSON and stop |

Output: `work/<campaign>/edits/<raw>_<id>.mp4` and `<raw>_<id>.plan.json`, both
listed in the workspace viewer (`python -m clipper serve`).

```
style profile ──▶ shot length, camera move, transition   ┐
transcript    ──▶ word gaps  (where cuts sound cleanest) ├──▶ plan.json ──▶ one
energy curve  ──▶ silences the words missed              ┘               ffmpeg run
```

### How it cuts

* **Plan first, render second.** `clipper/edit/plan.py` writes every cut as data
  - boundaries, per-shot camera move, transition, caption window - to
  `<clip>.plan.json`. `clipper/edit/render.py` then turns that plan into a single
  ffmpeg filtergraph. The plan is hand-editable: change a `start`/`end`, re-render
  with `--plan-only` off, and nothing else moves.
* **Shot lengths** come from `pacing.avg_shot_len`, jittered ±15% with a **seeded**
  random walk, so a given candidate always produces the same edit. Every shot is
  at least 0.7 s so nothing flickers.
* **Cut points snap to pauses.** Boundaries are built first, then each internal cut
  moves up to ±0.5 s to the nearest word gap and/or audio dip - clamped so shots
  can neither overlap nor drop below the minimum. The result is contiguous and
  covers the candidate window exactly, which is asserted in the tests.
* **Camera moves** come from the profile: one move per shot (punch-in ramps
  1.0 → `zoom.punch_in_scale` over `zoom.punch_in_duration`, measured on the
  reference videos), applied with `zoompan`, so it is a real ramp inside the shot
  and resets at every cut. `static` profiles hold still.
* **Transitions** are real blends now, not metadata: `cut`, `fade` (crossfade),
  `fade_black` (dip through black), `fade_white` (flash) or any of the 58 blends
  ffmpeg's `xfade` filter offers, by name. A blend takes a little from either
  side of the cut and shows both at once, so it costs one blend's length of clip
  time - `clip.blend_shortening` says how much, and every shot carries
  `out_start`/`out_end` so downstream stages can map source time to clip time.
  The renderer was verified against ffmpeg's actual `xfade` behaviour
  (`offset`, where the blend sits, when the output ends) rather than its docs:
  starting the blend *at* the cut instead of one blend-length before it mixes
  every frame with itself, which renders as a hard cut - which is exactly what
  the first implementation did, and what measuring the output caught.
* **Audio** is cut alongside the picture, so a laugh or a beat is not clipped
  mid-word; silent footage still renders, just without an audio track.

### Honest limits

* Blend timing is honest but coarse: a blend eats one `duration` of clip length
  (that is what a dissolve does), so a 16.35 s moment with seven 0.4 s dissolves
  renders as 13.55 s. Stage 4 does not stretch the source window to compensate.
* Blends are picture-and-sound dissolves; there is no beat-syncing, no sound
  effects and no per-shot blend choice yet (all listed in `FEATURES.md`).
* `zoompan` costs about one frame per shot, so a 16.35 s plan renders as 16.4 s.
  The renderer warns when the difference passes 0.35 s.
* If a plan asks for footage past the end of the file, the tail is trimmed to what
  exists and the plan's `clip.trimmed_to_source` flag records it - it never pads
  with a frozen frame.
* Captions are **not** burned in here: captions belong to stage 3 (`captions`) and
  the platform exports to stage 5. `python -m clipper captions <edit>.mp4` works on
  an assembled clip today.

Demo output (`python -m clipper edit campaign_demo --top 2`): two clips, 16.4 s /
8 shots and 13.7 s / 7 shots, each camera move ramping 1.00 → 1.12 inside every
shot and resetting at the cut. With `--transition fade` the same moment comes out
as `episode_01_01_fade.mp4`: a dissolve between every pair of shots, 2.8 s
shorter, and the cuts are gone from the pixels (the biggest frame-to-frame change
drops from 29 to 5 when measured frame by frame).

---

## The style profile

One JSON per campaign, `styles/<name>.style.json`, produced by stage 1 and
consumed by stage 3 (and later by stages 4-5). Every field has a default, so a
hand-written partial profile is valid:

```json
{
  "captions": {
    "font_family": "Montserrat",
    "font_size_ass": 104,
    "primary_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 6,
    "casing": "upper",
    "position": { "anchor": "bottom_center", "cy": 0.78 },
    "karaoke": { "enabled": true, "highlight_color": "#FFE14D" },
    "max_words_per_cue": 3,
    "max_lines": 1
  },
  "pacing": { "avg_shot_len": 1.8, "cuts_per_minute": 33 },
  "zoom": { "dominant": "punch_in", "punch_in_scale": 1.14, "punch_in_duration": 0.3 }
}
```

Full contract with all fields and defaults: `clipper/config.py` (`DEFAULT_STYLE`).
Field-by-field reference, including which values are measured vs inferred:
`docs/style-profile.md`.

---

## Layout

```
clipper/
├── cli.py            one entry point for every stage
├── config.py         paths, platform presets, default style profile
├── ffmpeg.py         process/probe/decode/encode wrapper (Windows-safe)
├── asr/              swappable speech-to-text: moonshine, faster_whisper, fixture
├── align/            silero VAD + energy alignment (word timings from plain text)
├── captions/         cues → .ass → burned-in video (stage 3)
├── edit/             plan + ffmpeg render of the cuts (stage 4)
├── ingest/           campaign scanning (stage 0)
├── select/           moment selection: energy, hooks, window growth (stage 2)
├── style/            style extraction from references (stage 1)
├── synth.py          synthetic footage with known ground truth (tests, samples)
├── serve/            local viewer for footage, styles and exports
└── util/             json, logging, timecode helpers
assets/fonts/         Montserrat (OFL) so rendering is identical everywhere
samples/              synthetic campaign, committed, regenerable
campaigns/            YOUR campaigns (gitignored)
styles/ work/ output/ generated; work/ and output/ are gitignored
```

## Tests

```bash
python -m pytest              # 167 tests, ~95 s
python -m pytest -m integration
```

The tests do not trust the code. Caption tests render a clip and inspect the
**pixels** for white glyphs, black outline and karaoke highlight colour. Style
tests recover values that were chosen before rendering: cuts at 2.0 s and 4.0 s,
a 1.13x punch-in, a 104 px font. Selection tests use an episode whose loud
stretches and hook sentences sit at known times. Edit tests render a clip and
**measure the camera in the output pixels** (`estimate_scale` over decoded frames)
and check a dissolve really dissolves (no single frame carries the change, and a
dip to black really reaches black), plus plans that must stay contiguous,
deterministic and inside the footage. The viewer tests run the real HTTP handler on
a real socket, because a `HEAD` that 501s or a `Range` that restarts from zero is
what makes a video preview look broken.

## Configuration

Any path can be overridden with environment variables:

```
CLIPPER_ROOT CLIPPER_CAMPAIGNS CLIPPER_SAMPLES CLIPPER_STYLES CLIPPER_WORK
CLIPPER_OUTPUT CLIPPER_MODELS CLIPPER_FONTS CLIPPER_FFMPEG CLIPPER_LOG
```
