# What clipper can do — the menu

Two lists. The first is **everything that already works** (run it today). The
second is **everything we can add next**, numbered, so you can just say the codes:
*"add V10, C2 and A5"* — and I'll build them in that order, one at a time, each
with tests, the way the stages have gone so far.

Codes: **V** cuts/motion · **C** captions · **A** audio · **S** style & moment
smarts · **E** export · **X** workflow & viewer.
Effort: **S** = one sitting, **M** = a real chunk of work, **L** = big.
"offline" means it needs no downloads and no GPU, which is the rule everything
here has followed so far.

---

## 1. What you have right now

Everything below runs in this sandbox: CPU only, no accounts, no paid tools,
FFmpeg 7.0.2 with libass. 161 tests cover it (`python -m pytest`).

### Stage 0 — look at a campaign
```bash
python -m clipper scan <campaign>          # probe every file into work/<name>/manifest.json
python -m clipper doctor                   # check ffmpeg, fonts, models, folders
python -m clipper samples                  # build the synthetic demo campaign
```

### Stage 1 — learn the style from your reference clips
```bash
python -m clipper style <campaign> [--fps 8] [--width 640] [--max-seconds 30] [--no-evidence]
```
Writes `styles/<campaign>.style.json` — hand-editable, every field optional:

* pacing: average/median shot length, cuts per minute
* zoom: `punch_in` / `slow_push` / `pull_out` / `static` / `mixed`, the scale it
  reaches and how long it takes
* captions: where they sit, cap height → ASS font size, primary/outline colours,
  karaoke highlight colour, UPPER vs as-written, words per cue, animation
* audio: loudness (EBU R128), speech ratio, whether a music bed runs under it
* confidences per section, human notes, and evidence PNGs of what it measured

Known-truth validation: synthetic clips made with 2.0 s cuts / 1.13× punch-in /
104 px captions read back as 2.0 s, 1.12×, 104 px.

### Stage 2 — find the moments worth clipping
```bash
python -m clipper select <campaign> [--top 8] [--min 20] [--max 60] [--platform reels] [--transcript PATH]
```
Writes `work/<name>/candidates/*.json` + a readable `report.md`. Loud stretches
are measured against the clip's own baseline; hook sentences are scored by a
readable rule set (questions, numbers, money, list promises, contrarian claims,
stakes, emotion, second-person; filler penalised). One moment per burst, one clip
per moment, edges snapped to pauses, and it still works with no transcript at all.

### Stage 3 — word-level captions
```bash
python -m clipper transcribe FILE [--asr moonshine|faster_whisper|fixture] [--model small]
python -m clipper captions FILE [--campaign NAME | --style PATH] [--platform tiktok|reels|shorts]
                                [--fit cover|blurpad|none] [--mode line|word]
                                [--max-words N] [--ass-only] [--out PATH]
```
Writes `transcript.json`, `cues.json`, `captions.ass` and a burned-in 1080×1920
mp4, styled from the profile (font, size, colour, outline, karaoke highlight,
position). Speech recognition is real and offline: Moonshine (weights ship inside
the wheel), with an energy aligner for word timings; faster-whisper if you install
it where the model can be downloaded.

### Stage 4 — assemble the clip
```bash
python -m clipper edit <campaign> [--top N] [--ids "#01,#03"] [--shot-len 1.4]
                                 [--platform tiktok|reels|shorts] [--focus centre|top|bottom]
                                 [--transition cut|fade|fade_black|wipeleft|circleopen|...]
                                 [--transition-duration 0.4] [--tag fade] [--plan-only]
```
Writes `work/<name>/edits/<file>_<id>[_tag].mp4` and a readable `.plan.json`:

* shots cut to the profile's pacing (seeded, so a re-render is identical), never
  shorter than 0.7 s, snapping to word gaps and silences
* a camera move inside every shot (punch-in ramps, resets at each cut)
* **58 blends by name**: `fade`, `fade_black`, `fade_white`, `wipeleft`,
  `circleopen`, `zoomin`, `squeezeh`, `pixelize` … (aliases like `dissolve`,
  `dip to black`, `flash` map to the right one; an impossible name falls back to
  a hard cut and says so in `plan.notes`)
* the plan records the exact timeline (`out_start` / `out_end` per shot, and
  `clip.blend_shortening`), so captions and exports know where everything lands
* 1080×1920 per platform preset, audio cut with the picture, silent footage still
  edits, a plan that runs past the end of the file trims instead of padding

### Viewer — watch everything in the browser
```bash
python -m clipper serve [--port 8000]
```
Campaign folders and their references/raw files, candidate moments as **seekable
players** (they start at the moment), assembled clips with their plan summary,
style profiles, and work files. Range requests work, so seeking works.

---

## 2. The menu — what we can add

### V — cuts, motion and transitions
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| V1 | Beat-synced cuts | cut on the music's beats/onsets instead of every ~2 s (reuses the beat detection from your montage editor) | M |
| V2 | Per-shot blend taste | blend only where it helps (first/last shot, scene changes), alternate blend styles, "fade in at the start / out at the end" | S |
| V3 | Zoom transitions | punch through into the next shot (`zoomin`, blur, whip) rather than a plain dissolve | M |
| V4 | Reaction cutaways | keep a wide shot while a laugh/reaction lands, then cut back | M |
| V5 | B-roll inserts | cut away to a clip/image while the voice keeps talking (drop files in `broll/`) | M |
| V6 | Speed ramps | slow-motion on a punchline, 1.25× to tighten dead air | S |
| V7 | Split screen / stacked two-shot | for interview and podcast footage | M |
| V8 | Ken Burns on stills | zoom/pan over an image or a frozen frame | S |
| V9 | Impact & shake | shake, glitch, flash on a beat or an emphasis word | S |
| V10 | Silence tightening | jump-cut the dead air out, with a small zoom to hide the cut — the single biggest win on podcasts | S |
| V11 | Shot entrance motion | a scale-pop on every cut instead of a static frame | S |
| V12 | Hook-first opening | start on the strongest sentence, then rewind into the clip | M |
| V13 | Multi-moment clips | stitch 2–3 candidates into one longer story clip | M |
| V14 | Storyboard renders | one variant per cut pattern so you can pick, instead of one take | M |

### C — captions
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| C1 | Word pop-in animation | each word scales/pops in as it is spoken (karaoke colour exists already) | S |
| C2 | Keyword emoji | 💰 for money, 🔥 for hype — a small offline keyword→emoji map, emoji font bundled | S |
| C3 | Auto-highlight numbers & names | money, %, dates, names drawn in the accent colour | S |
| C4 | Censor bleeps | profanity muted or beeped, with the caption dotted out | S |
| C5 | Speaker colours | different caption colour per speaker | S (see S4) |
| C6 | Translation | captions in another language | L — needs a model we cannot download in the sandbox |
| C7 | Safe-area presets | keep captions clear of TikTok/Reels UI buttons and the profile line | S |
| C8 | Smart fitting | long words shrink, cues re-wrap so nothing clips off screen | S |
| C9 | Caption templates | boxed, outlined, shadowed, highlight-box, "big bold" presets | S |
| C10 | Two-line bilingual | translation on a second line under the first | S (see C6) |
| C11 | Per-syllable bounce | karaoke that bounces per syllable instead of a colour sweep | M |
| C12 | Caption QA sheet | contact sheet of every cue rendered, to check styling at a glance | S |

### A — audio
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| A1 | Loudness normalise on export | two-pass EBU R128 to each platform's target (−14 LUFS TikTok, etc.) | S |
| A2 | Music bed with ducking | background track that ducks under speech (you supply the tracks) | M |
| A3 | Ducking only | no music, just automatic level riding around speech | S |
| A4 | Silence removal | already useful with V10, exposed as its own audio-only pass | S |
| A5 | Whoosh / pop sound effects | synthesised in numpy — no assets needed — on cuts, zooms and beats | S |
| A6 | Voice clean-up | high-pass, de-hum, de-ess, gentle compression (ffmpeg filters) | S |
| A7 | Laugh & applause detection | spot reactions to zoom or add an SFX | M |
| A8 | Filler-word removal | "um", "uh", "like" cut out with jump cuts, transcript-driven | M |
| A9 | Noise reduction | `afftdn` profile for hissy rooms and phone mics | S |

### S — style learning & moment smarts
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| S1 | Learn transitions from references | measure whether cuts are hard, dipped or dissolved, so `transitions.in` is learned instead of guessed | M |
| S2 | Per-shot camera moves | today the profile's *dominant* move is used for every shot; learn the real mix | M |
| S3 | Font shortlist | rank candidate fonts by glyph shape instead of leaving `font_family` null | M |
| S4 | Speaker diarization | who spoke when | L — needs a model, offline path is uncertain |
| S5 | Learn from your choices | mark candidates good/bad in the viewer and the hook score is tuned on your picks | M |
| S6 | Diversity in candidates | stop three clips coming from the same 10 seconds | S |
| S7 | Length variants | 15 s / 30 s / 60 s versions of the same moment in one run | S |
| S8 | Cover-frame picker | choose the most expressive frame as the thumbnail | M |
| S9 | Titles & hashtags | offline, transcript-driven suggestions for the caption/description | S |
| S10 | Music/beat analysis | tempo, downbeats and drops so V1 has something to sync to | M |

### E — export and publishing
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| E1 | Stage 5 export presets, properly | per-platform encode: resolution, bitrate ladder, fps, loudness, faststart | S |
| E2 | Other shapes | 1080×1080 square, 16:9 landscape, 1440p variants | S |
| E3 | Batch everything | every candidate × every platform in one command | S |
| E4 | Metadata sidecar | title, description, hashtags written next to each clip | S |
| E5 | Thumbnail export | a cover frame per clip | S |
| E6 | Direct upload | post to TikTok/YouTube/Instagram — needs each platform's API and your credentials | L, not offline |
| E7 | Branding overlay | logo/watermark and a handle line in a safe corner | S |
| E8 | Progress & resume | ETA per clip, skip work that is already rendered | S |

### X — workflow and viewer
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| X1 | One command, whole pipeline | `python -m clipper run <campaign>`: scan → style → select → edit → captions → export | S |
| X2 | A/B compare in the viewer | fade vs cut, variant vs variant, side by side | S |
| X3 | Approve / reject moments | pick the keepers in the viewer; stage 4 edits only those | M |
| X4 | Trim by dragging | adjust a candidate's in/out in the browser | M |
| X5 | Live progress in the viewer | watch a long render tick along | S |
| X6 | Dry-run tables | print the plan as a table without rendering (`--plan-only` exists; this adds a preview table + timing estimate) | S |
| X7 | Demo with real speech | a small committed speech sample so captions/selection/audio can be tried without your own footage | S |
| X8 | Your-machine install | install docs and path handling for a normal Windows/Linux box | S |
| X9 | Cache & skip | re-renders skip shots and clips that have not changed | M |
| X10 | Watch a folder | drop a new recording in and clips appear | M |

---

## 3. If you want my pick

* **V10 silence tightening** and **A8 filler removal** — the two things that make a
  long podcast feel professionally clipped, and both work off data we already have.
* **S1 learn transitions from references** — closes the last gap in "learn the
  style from the references": everything else about the references is measured,
  the cut look is currently assumed.
* **E1 + A1 stage 5 export** — the one stage that is still missing; without it you
  have mezzanine clips, not platform-ready files.
* **C1/C9 caption polish** — captions are the star for Whop campaigns; pop-in and
  template presets are cheap and very visible.

## 4. Not on the menu (and why)

* **Anything with a cloud API** (OpenAI, ElevenLabs, hosting) — you said
  everything runs here, free and offline.
* **Model downloads that need release assets** — those are blocked in this
  sandbox, so diarization and translation would only work on your own machine.
* **GPU-only paths** — no GPU here, so everything stays CPU-sized.
