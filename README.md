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
| 2 | moment selection from raw (speech energy, hooks, laughs, topic turns) | planned |
| 3 | `captions` — word-level ASR, styled captions, 9:16 burn-in | **done** |
| 4 | edit assembly (cuts, zooms, transitions to profile) | planned |
| 5 | `export` — platform presets | planned (presets exist, used by stage 3 already) |

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
├── captions/         cues → .ass → burned-in video (stages 3)
├── ingest/           campaign scanning (stage 0)
├── serve/            local viewer for footage, styles and exports
└── util/             json, logging, timecode helpers
assets/fonts/         Montserrat (OFL) so rendering is identical everywhere
samples/              synthetic campaign, committed, regenerable
campaigns/            YOUR campaigns (gitignored)
styles/ work/ output/ generated; work/ and output/ are gitignored
```

## Tests

```bash
python -m pytest              # 45 tests, ~50 s
python -m pytest -m integration
```

The caption tests do not trust the code: they render a clip and inspect the
**pixels** for white glyphs, black outline and karaoke highlight colour.

## Configuration

Any path can be overridden with environment variables:

```
CLIPPER_ROOT CLIPPER_CAMPAIGNS CLIPPER_SAMPLES CLIPPER_STYLES CLIPPER_WORK
CLIPPER_OUTPUT CLIPPER_MODELS CLIPPER_FONTS CLIPPER_FFMPEG CLIPPER_LOG
```
