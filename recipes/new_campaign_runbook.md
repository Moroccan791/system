# New campaign runbook — raw video in, post folders out

## House rules (the user's standing decisions — never re-litigate)

- **The user only judges content.** They send raw video + reference +
  the campaign's Google Doc; everything else (sourcing, editing,
  captions, packaging) is the agent's job. Never hand homework back.
- **Every clip**: one purpose, self-contained, a hook in the first
  seconds (contrast / confession / number / defiance — ranked by the
  agent, hooks first, polish after), and a real ending: closing line +
  fade-out (picture and audio) + outro text. Never mid-topic, never an
  abrupt cut.
- **Hook-first selection** (the editor spec): the clip starts on the
  claim / number / surprise / punchline — never a throwaway lead-in
  ("so", "no offense", "okay", "you see"); setup is cut to one short
  line or dropped. The on-screen headline must match what is said in
  the first 2 s. Default length 25–40 s unless the story needs more
  (a campaign doc's window overrules). End on the punchline or an
  open loop, never mid-sentence. Each clip of a batch takes a
  different segment, hook and framing — hooks must mesmerize:
  contrast / confession / number the viewer *feels*.
- **Captions** reproduce what was actually said, in true sync with the
  voice (engine-level; never hand-tune one clip — fix the pipeline):
  **2–4 words at a time, max two lines**, one fixed lower-centre
  position, one style all video, never over the face or hands, the
  spoken/key word in the project accent. 18+ words are starred
  (`s*x`, `f*ck`). Big-word accent colour is the user's pick per
  project, never imposed.
- **Typing sound** (default ON, `--typing-sound on|off`): the hook
  headline types on word by word; every keystroke is one of five
  synthesized key clicks (`assets/sfx/keys/`, CC0 — see
  `assets/sfx/LICENSES.md`), random pick, ±10% volume / ±3% pitch,
  an "enter" click to finish, ≈ −25 dB under the voice; caption
  blocks land with a much lighter tick. Off also stops the headline
  typing (never type silently).
- **Next-level format available** (`--mode poster`): centre-frame
  poster captions, kinetic claim cards (`--card`), proof stickers
  (`--sticker`), accumulating lists (`--list`) and ducked music beds
  (`--music dark|bright|chill`) — the grammar decoded in
  `recipes/next_level_format.md`. Use it for explainer-style clips;
  QC's `visual_pacing` check (event every ≤3.5 s) gates it.
- **Automated QC after every render**: `<video>.qc.json` lands next
  to the output (also `clipper qc VIDEO --ass … --transcript …
  --hook "…"` standalone): first caption ≤ 1 s, no caption over a
  face (YuNet), no static background > 4 s, loudness in window,
  headline ↔ first-2 s overlap, duration, corner-logo scan. A FAIL
  is reported in the render warnings — read it before packaging;
  fix the cause, never hand-wave it.
- **Framing**: faces fully in frame, always (an ear cut off = rejected
  clip). One continuous gentle push; camera punches only on payoff
  words; per-segment reframe when speakers sit in different places.
- **B-roll**: full-frame cutaways only, at most one or two, never pasted
  over a face, never "extra". Images are generated or campaign-supplied
  (licensing) — stock with watermarks is a no.
- **Sound**: sound design on (riser, payoff pops, quiet whoosh/hit on
  punches and cuts), loudness normalized, music (if any) ducked under
  the voice; typing sound as above, sitting far under the voice.
- **Deliverable per clip** = video(s) + posting pack (title,
  per-platform description, 7–8 hashtags) in a `post<N>/` folder in
  this repo — the user downloads from GitHub, the preview does not
  work for them. Campaign docs rule each brief: tags, handles,
  watermark, banned topics/claims, duration windows.
- **Quality chain is automatic**: crf16/medium mezzanine, lanczos,
  denoise + cas sharpen. The biggest quality lever left is the user's:
  raws downloaded at the highest quality available (1080p+).

## The course rules, now enforced (2026-10-20)

The campaign supplied a clipping course ("Clipping 101"). Its editorial rules
are now code, not intentions - they were applied by hand before, which is how
shipped files ended up with 24-character caption lines and a visible "um":

| Rule (course wording) | Where it lives | Fails the render? |
|---|---|---|
| "1-2 lines max, ~14 characters per line" | `scripts/whop/caption_rules.py` (`wrap_cells`, `card_report`) | yes, over 17 chars or 3+ lines; warns when >25% of lines exceed 14 |
| "Trim uh, um, you know, like" | `caption_rules.filler_words` | yes, any filler left in the kept speech |
| "Hook in the first 2 seconds, never a throwaway lead-in" | `qc_gate.py:check_hook` + `campaign_rules.json` | yes |
| "Cut at the emotional peak" | `tight_posts.py --end=peak` (cuts on the last word, no CTA card) + `ending_tail` check | warns over 2 s of tail |
| "Voice is always the loudest element" | `qc_gate.py:check_audio`, measured in the 250-3500 Hz voice band | yes, under 12 dB over the bed |
| "No black bars" | `qc_gate.check_picture`, footage frames only, end card exempt | yes |
| "Never over the face" | `qc_gate.check_picture`, YuNet score >= 0.62 and >35% of the box in the band | yes |
| "No static visuals" | `qc_gate.check_picture`, frozen stretch > 3 s | yes |
| Duration window | `campaign_rules.json` (hard 12-60 s, preferred 25-40 s) | hard fail outside, warn outside preferred |

Run it after every render:

    .venv/bin/python scripts/whop/qc_gate.py <video> --manifest work/street/<post>/tight_cards.json

The report lands next to the video as `<video>.qc.json`. Per-campaign numbers
live in `campaigns/<campaign>/campaign_rules.json` - never hard-code them in a
script, and never lower a limit to make a render pass.

Two habits the course is really about, which no gate can do:
- **`RESULTS.md`** in the campaign folder: every post's views, watch time,
  first cliff and US%, plus a verbatim "mistake list" of every note. Fill it
  48 h after posting; the next batch is cut against it.
- **`recipes/distribution_playbook.md`**: the Tier-1/US account setup and the
  80%-US check. A clip that holds watch time and gets no reach is a
  distribution problem, not an editing one.

## The fast path

Everything below is one command per step; the slow one-off work
(watermark engine, per-segment reframing, quality chain) is already in
the pipeline. If the sandbox was reset, run `bash scripts/bootstrap.sh`
first (rebuilds `.venv` + the face model), then
`git fetch && git reset --hard origin/arena/14b1cc76-system` if the
checkout rolled back — work is always committed before delivery, so
nothing is ever lost, only scratch (`work/`, `output/`) is rebuilt.

## 0. Intake

- Media arrives as commits on `main` (or a folder the user names, e.g.
  `campaign 2/`). Pull it out:
  `git show "origin/main:<path>" > campaigns/<campaign>/raw/<file>`
- Read the campaign's Google Doc (fetch the export URL) and write the
  rules into `styles/<campaign>.style.json` (copy the shape of an
  existing profile: captions block config, `fade_out_seconds`,
  `outro_text`, grade with denoise/sharpen, `word_fixes`).
- **Branding rule the user set**: a watermark image only when the
  campaign sends one (`--watermark FILE,tr,0.30`); otherwise the pinned
  text handle (profile `captions.handle(s)` / `--handle`). The accent
  colour is the user's pick for the project (`--accent gold|lime|...`).

## 1. Transcribe (background — the only slow step)

```
mkdir -p work/<stem>
.venv/bin/python -m clipper transcribe <raw> --out work/<stem>/transcript.json
```
(~0.7× real time with moonshine; start it first, scout moments meanwhile.)

## 2. Pick moments from the transcript, not by scrubbing

Read the timed transcript and choose self-contained windows: a hook in
the first seconds (contrast / confession / number / defiance), one
purpose, a real ending (payoff line + reaction beat), inside the
campaign's duration window. Before locking a window, check:

- **Compliance grep**: profanity scan of the transcript; the campaign's
  banned topics/claims/brands (per the doc in the style profile notes).
- **The speaker is actually on screen** through the window.
- **Source-burned text**: grab frames inside the window. If the source
  itself flashes text (gag captions, stickers), make sure it either fits
  inside the 9:16 crop or stays out of it — a half-cut foreign caption
  is a rejected clip. (This killed the first MILK XP funny pick.)

Write the winner(s) to `campaigns/<campaign>/candidates/manual_*.json`
(committed = reset-proof; `edit` reads `work/` first, then falls back
to this folder) and copy to `work/<campaign>/candidates/`.

## 3. Reframe (multi-speaker sources)

```
.venv/bin/python -m clipper reframe <raw> <start> <end>
```
Prints the `segments` array (source cuts + YuNet face-median focus per
span) — paste it into the candidate. Single-speaker centred sources can
skip this and use one `--focus-x` measured from a couple of frames.

## 4. Edit + captions (per platform)

```
.venv/bin/python -m clipper edit <campaign> --ids F2 --tag grade \
    --zoom push --shot-len 60 --focus-x 0.4
.venv/bin/python -m clipper captions <edit.mp4> --campaign <campaign> \
    --platform tiktok --plan <edit.plan.json> --transcript <transcript.json> \
    --accent <user pick> --hook "LINE ONE|LINE TWO" \
    --watermark campaigns/<campaign>/watermark.png,tr,0.30 \  # if sent one
    --sound [--fix wrong=right] --out output/<name>_<platform>.mp4
```
Re-render once per platform that needs a different burned handle;
identical-content platforms (Shorts/TikTok with no handle) still get
their own encode preset. ~1–3 min per render; the full polish stack
(ticks, riser, word-pop, fade-out + outro, lanczos/denoise/sharpen
quality chain) is automatic.

## 5. Verify before packaging (non-negotiable, ~1 min)

Four frames from each final: hook (1 s), payoff, last caption, outro.
Read them: faces fully in frame, caption text = what was actually said
and fits the width, watermark/handle clear, ending fades on a closing
line. If a face grazes an edge, it's the reframe map — fix the segment
focus, not the caption.

## 6. Package + ship

`post<N>/` at repo root: the platform mp4(s) + a `cover.jpg` + `post.txt`
(video name, handle/tag, title, per-platform description, 7–8 hashtags,
any posting rules from the brief). The cover is composed from the
rendered clip's payoff frame (so its handle/watermark is already on it):
```
.venv/bin/python -m clipper cover <final.mp4> post<N>/cover.jpg \
    --at <payoff-ts> --text "HOOK LINE|SECOND LINE" --accent <user pick>
```
Full-frame B-roll cutaways already drift (slow push-in) and fade in the
captions pass — stills that sit frozen read as pasted photos. And one
more B-roll rule from the user: premium, story-matched, at most one or
two per clip — never extra. `git add -f` the mp4s (media is gitignored),
commit, push `arena/14b1cc76-system`, present the TikTok/first file.
**Before ending the turn, `git status` must show no untracked
deliverables** — untracked files are exactly what sandbox resets eat.

---

## Render recipes (verbatim, for instant re-renders)

### Sartain — dating apps math (was post1; edit tag `e2e`, focus 0.70)
```
clipper edit michael_sartain --ids S2 --tag e2e --zoom push --shot-len 60 --focus-x 0.70
clipper captions <edit> --campaign michael_sartain --platform <tiktok|reels|shorts> \
  --plan <plan> --transcript work/<XrdX stem>/transcript.json --accent gold \
  --hook "WOMEN MATCH 10%|MEN: 6 IN 1000" --whoosh 42.9 --punch --sound --tighten \
  --insert "40.6,1.8,assets/broll/dating_app_916.jpg,full" --out output/...
```

### Sartain — five months (was post2; edit tag `calmpush`, focus 0.69)
```
clipper edit michael_sartain --ids B1 --tag calmpush --zoom push --shot-len 60 --focus-x 0.69
clipper captions <edit> --campaign michael_sartain --platform <tiktok|reels|shorts> \
  --plan <plan> --transcript work/<Beta stem>/transcript.json \
  --hook "HE WAITED|5 MONTHS" --whoosh 34.6 --punch --sound --tighten \
  --insert "3.05,1.4,assets/broll/calendar_months.jpg,full" --out output/...
```
(Profile carries the rest: fade/outro, per-platform handles,
`word_fixes fence->offense`, grade.)

### MILK XP EP.3 — students grade the teacher (post3, candidate #F2)
```
clipper edit milkxp_ep3 --ids F2 --tag grade --zoom push --shot-len 60 --focus-x 0.4
clipper captions <edit> --campaign milkxp_ep3 --platform <tiktok|shorts> \
  --plan <plan> --transcript work/MilkPEP_milkXP_Episode3_YT_16x9/transcript.json \
  --accent lime --hook "THE STUDENTS|GRADED THE TEACHER" \
  --watermark campaigns/milkxp_ep3/watermark.png,tr,0.30 --sound --fix n=an
```

### MILK XP EP.3 — milk line bloopers (post4, candidate #M1)
```
clipper edit milkxp_ep3 --ids M1 --tag milk --zoom push --shot-len 60 --focus-x 0.58
clipper captions <edit> --campaign milkxp_ep3 --platform <tiktok|shorts> \
  --plan <plan> --transcript work/MilkPEP_milkXP_Episode3_YT_16x9/transcript.json \
  --accent lime --hook "HE KEPT MESSING UP|THE MILK LINE" \
  --watermark campaigns/milkxp_ep3/watermark.png,tr,0.30 --sound --fix gray=Greg
```
