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
FFmpeg 7.0.2 with libass. 242 tests cover it (`python -m pytest`).

### Stage 0 — look at a campaign
```bash
python -m clipper scan <campaign>          # probe every file into work/<name>/manifest.json
python -m clipper doctor                   # check ffmpeg, fonts, models, folders
python -m clipper samples                  # build the synthetic demo campaign
```

### Getting the footage in when the chat upload does not land
```bash
python -m clipper drop <campaign> --how                      # print instructions
python -m clipper drop <campaign> --branch footage           # pull them down
python -m clipper drop <campaign> --branch footage --dry-run # just look
python -m clipper drop <campaign> --branch footage --into raw --overwrite
```
Fetches one branch of this repo, pulls the media out of it, sorts it into
`references/` and `raw/` (by filename hint, then by length) and copies it into the
campaign. Idempotent, never clobbers a differently-sized file, never merges.
It exists because GitHub is reachable from both sides of the sandbox and a chat
upload is not always.

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

### Getting footage in when the chat upload does not land
```bash
python -m clipper drop <campaign> --how                        # instructions
python -m clipper drop <campaign> --branch main                # pull them down
python -m clipper drop <campaign> --branch main --dry-run      # just look
python -m clipper drop <campaign> --branch main --into raw --overwrite
```
Fetches one branch of this repo, takes the media out of it, sorts it into
`references/` and `raw/` (by filename hint, then by runtime) and copies it into
the campaign with the original names. Idempotent, never clobbers a
differently-sized file, never merges. It exists because a chat upload is not
always the road that works and GitHub is reachable from both sides.

### Campaign rules — the brief as data, checked per clip
```bash
python -m clipper rules <campaign>          # show the rules in force
python -m clipper rules <campaign> --init   # write a template to fill in
python -m clipper select <campaign> [--keep-banned]
```
`campaigns/<name>/campaign.json` holds clip length window, hook window, approved
and banned topics, banned names, retired phrases, tone warnings and brand notes.
Selection drops moments that break a rule (reporting why), lifts the ones that
fit, trims long lead-ins so the hook lands in the first seconds, and stamps a
`compliance` block on each candidate. Keyword lists are literal by design.

### Captions that inherit the source timings, not a re-guess
```bash
python -m clipper captions <clip>.mp4 --campaign <campaign> \
    --plan work/<campaign>/edits/<clip>.plan.json
```
An assembled clip has already been cut, so recognising its audio again both
wastes a pass and drifts (measured on a real 20.5s clip: up to +0.9s by the
last word, because an energy aligner re-run on cut-up speech loses the thread).
With `--plan`, the source transcript's own timings are carried through the cut
- shot by shot, clamped at the joins, words in dropped source removed - so
captions land where the words were actually said (mean error 0.012s, max 0.23s
versus 0.37s / 0.97s the other way). It is also about twice as fast, because
there is no speech recognition pass at all.

### Blends — see the transitions instead of guessing
```bash
python -m clipper blends [--all] [--list] [--seconds 1.4] [--size WxH]
python -m clipper blends --source raw/ep.mp4 --a 12.0,13.4 --b 40.0,41.4
```
Renders the same pair of shots once per blend with the name burned in, so you can
scrub through and pick. The 58 names are ffmpeg's, read from the binary.

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
| S9 | **Shipped**: `clipper arcs <transcript> [--source V --campaign C]` - story-arc selection (select/beats.py): hook (question) -> build -> payoff (number/conclusion) -> ends at the first real silence with a capped reaction tail. Crosstalk that never breathes is reported *unbounded*, a short beat is reported *too short* - never padded into a fake arc. Written candidates feed `clipper edit` directly | done |
| C0e | **Shipped**: `--insert` defaults to `full` - a timed image is a full-frame *cutaway* (the tutorial pattern, and the reviewer's fix: never paste art across the subject's face); `middle`/`top_safe` remain for deliberate overlays | done |
| A9 | **Shipped**: asset libraries sourced in-repo, no user homework: `assets/sfx/` (whoosh/riser/pop, synthesized in pure Python - CC0 by construction) and `assets/icons/` (Twemoji v14.0.2, CC-BY 4.0, renamed to spoken words for matching) | done |
| V10 | **Shipped**: `--tighten [--tighten-gap S]` - silence tightening as a captions stage: pauses >= 0.6s (default) shrink to a ~0.22s breath; words carry through the cuts via the shot-plan remapper and whoosh/insert times are remapped with them, so captions, punches and sfx stay in sync with no second ASR pass (`clipper/captions/tighten.py`) | done |
| S10 | **Shipped**: `--sound` - sound design from the CC0 library: a riser swelling under the hook plus one pop per camera-punch word, mixed with `amix ... normalize=0` so effects never turn the voice down (the default mix did, by -12dB; measured and fixed) | done |
| V5b | **Shipped**: B-roll cutaways keep their captions: inserts overlay *before* the subtitles burn, so the words keep talking over the image. Demo assets in `assets/broll/` (dating-app phone over the 68% line; calendar pages over "five months") | done |
| V0d | **Shipped**: `--punch` - camera punches: gaussian zoom spikes on the biggest caption words (numbers punch hardest, the climax always keeps a slot), proven on a synthetic grid (`tests/test_punch_grid.py`) because keypoint measurements lie on talking-head footage | done |
| S11 | **Shipped**: caption typing ticks - a soft keyboard click the moment each caption block lands (part of `--sound`; `captions.tick_volume`, default 0.16; two alternating synthesized clicks so it never sounds like a metronome) | done |
| C0f | **Shipped**: pinned handle - `captions.handle` / per-platform `captions.handles` burns the creator's @ at the right edge for the whole clip: the campaign's in-video tag requirement, met by construction instead of remembered per post | done |
| A10 | **Shipped**: word fixes as data - `captions.word_fixes` in the creator profile (or `--fix wrong=right` per render): mis-transcriptions corrected before timing/tightening/captioning, punctuation- and case-preserving. Standing example: `fence` -> `offense` for Sartain | done |

| C0 | **Shipped**: `--mode block` - the tutorial caption grammar as code. Words reveal exactly when spoken and stay until the sentence clears; the operative word sits bigger (auto-picked: numbers and content words beat "getting"); every word fades in with the same small rise; blocks clear the instant the next one starts. Never overedits by construction | done |
| C0b | **Shipped**: the bottom fade bar - a black gradient drawn as ASS vector strips behind the caption zone, sized from the profile's margin, so white text sits down on any footage | done |
| C0c | **Shipped**: `grade` section in the style profile: `{"vignette": 0.26, "contrast": 1.05, "saturation": 1.06}` burned in *before* the subtitles - the "cinematic look" from the tutorials, kept subtle on purpose | done |
| C0g | **Shipped**: quality chain for faces - the edit mezzanine renders at crf 16 / preset medium (was 18/veryfast, which smeared faces before captions ever saw them), every scale uses `flags=lanczos`, and the grade can open with `denoise` (`hqdn3d`) and close with `sharpen` (`cas`) from the profile (`denoise: 0.6, sharpen: 0.35` for Sartain). Burn-side enhancement alone measured ~nothing on an already-degraded mezzanine; the win comes from not destroying the detail upstream | done |
| C0d | **Shipped**: `--insert T,DUR,FILE[,middle|top_safe]` (repeatable) - overlays a still on the clip, alpha-faded, exactly when the word lands. Assets live in `campaigns/<c>/broll/`; the user supplies them (Freepik/Pinterest, per the tutorials). Keyword auto-matching filenames->words is the remaining piece of V5 | done |

| V0c | **Shipped**: `--zoom punch|push|pull|mixed|static` picks the per-shot camera move at render time. `punch` = a punch-in that settles on every cut, `mixed` = punch in on a share of them (`punch_in_ratio` in the style profile, default 0.5, the opening shot always moves). The extractor's honest "the references are mostly static" no longer forces a static clip: the profile records both the measurement and the chosen move. A pull is rendered as starting zoomed and settling, never below 1.0 (zoompan pads below that) | done |
| V0 | **Shipped**: `--focus-x 0.0-1.0` moves the 9:16 window sideways across the slack, for the many studio shots where the person who matters is off centre (`--focus` still picks the vertical band). On a real podcast this was the difference between a clip of Michael and a clip of his chair | done |
| V0b | **Shipped**: hand-picked moments. `select` writes candidates, but stage 4 reads whatever is in `work/<campaign>/candidates/` — drop a JSON with one window in it (id, start, end, duration, text) and `edit --ids "#68"` assembles it. The machine proposes; you can overrule | done |
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

### G — campaign compliance (started, more to come)
| Code | Feature | What it changes | Effort |
|------|---------|-----------------|--------|
| G0 | **Shipped**: moments under the floor are now *grown* to the campaign minimum (borrow the next sentence, then the one before it, then at most 2.5s of room tone; never past a banned topic, never across more than 1.2s of silence) instead of failing the length check | done |
| G1 | Face coverage check | measure "a face is on screen for X% of the clip" with an offline detector (~90 MB wheel) instead of reporting it as unmeasured | M |
| G2 | Word-form expansion for rules | match "dollars"/"bucks"/"salary" automatically for the `money` rule, with the expansion visible | S |
| G3 | Tone classifier | flag rage-bait / demeaning framings beyond an explicit word list | L — needs a model |
| G4 | Compliance check before upload | re-check the finished 9:16, captioned file (length, aspect, caption presence) rather than the source window | S |
| G5 | Multi-campaign rule sets | one workspace, several campaigns with different briefs, no cross-contamination | S |

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
