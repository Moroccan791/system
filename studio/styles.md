# The style shelf — five new references, read

Every reel below went through the same instrument (`studio/study.py`), so the
numbers are comparable: same cut detector, same luma/saturation measurement,
same kick grid. Contact sheets are in `work/study/<name>.jpg`.

Read this as *invariants*, not surface. What is written down for each style is
the thing that still holds when the footage changes — pacing, where type lives,
how the frame is shaped, what the grade does to a face — not the shots.

---

## The table

| style | file | frame | fps | len | cuts | median shot | longest | time in 4s+ holds | blur-whips | type on screen | cuts on a kick | luma | sat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `cold_read` | v5 | 1280×640 (2:1) | 30 | 31.7 s | 24 | 1.03 s | 6.50 s | 21% | 1 | 27% | 6/24 | 19 | 0.59 |
| `hype` | v11 | 1276×718 | 24 | 31.5 s | 38 | 0.71 s | 2.38 s | 0% | 6 | 49% | 14/38 | 35 | 0.37 |
| `square` | v12 | 720×720 (1:1) | 30 | 30.2 s | 14 | 1.33 s | 4.57 s | 44% | 3 | 16% | 4/14 | 37 | 0.61 |
| `hymn` | v13 | 1280×720 | 24 | 31.6 s | 15 | 1.79 s | 4.04 s | 13% | 0 | 69% | 2/15 | **11** | 0.35 |
| `barrage` | v26 | 1280×720 | 30 | 37.2 s | 52 | 0.53 s | 3.10 s | 0% | **14** | 36% | 16/52 | **85** | 0.33 |
| *(ref2)* | gwen | 1280×532 | 30 | 58.5 s | 33 | 1.00 s | 11.07 s | 43% | 0 | 41% | 3/33 | 29 | 0.49 |
| *(house)* | Zaalima | 1920×1080 | 30 | 34.9 s | 75* | 0.53 s | 1.27 s | 0% | 0 | 74% | 16/75 | 15 | 0.23 |

\* the instrument reads our own flash frames as extra cuts — the plan behind
that file is 49 cuts. Use these columns for *ranking*, not for absolute counts.

---

## 1. `cold_read` — v5, "Arey Peter"

**What it is.** The quietest edit on the shelf. A letterboxed 2:1 frame that is
never cropped, a very dark grade (median luma 19) with high saturation (0.59) so
skin reads warm against blue, and dialogue set as **short fragments in the
bottom-left corner**, all caps, small, plain white, no animation.

**The invariant.** The words are *pieces of a sentence split across cuts* —
"YOU DON'T MEAN" … "AND" … "AND I BEEN TRYING TO SAVE MY LIFE" … "I LOVE YOU."
Each fragment arrives on its own shot and dies with it. Type never sits on screen
between cuts; it is a subtitle, not a title. The edit then stops cutting entirely
and holds one 6.5 s shot at the end with nothing on it.

**Numbers that matter**
- 24 cuts in 31.7 s; median 1.03 s; one 6.5 s hold carrying 21% of the runtime.
- Type present only 27% of runtime, in 14 separate runs, all low-left (y 0.3–0.5),
  all narrow (0.08–0.33 of frame width). It clears 8.6 s before the end.
- Only 1 blur-whip in the whole file. Cuts are not on the beat (6/24) — the
  cutting follows the dialogue, not the music.

**What building it needs.** A fragment-caption type engine (small, lower-left,
kill-on-cut), a "hold the last shot" rule, and a slow planner profile. The
letterbox is a *presentation* choice, not a crop — it costs nothing.
**Cost: low.** No new fx.

---

## 2. `hype` — v11, "$2 BILLION"

**What it is.** The loud one. Giant condensed all-caps set **wide, behind the
subject**, arriving in pieces at huge size — "I'M A TRAGE", "DEFE", "TAKE IT AS
A", "PRIDE" — so the word is bigger than the frame and you read it as texture
before you read it as a word.

**The invariant.** Type sits *behind* the person, not over them, and its scale is
absurd — widths of 0.8–1.0 of frame. That is the whole trick, and it is also the
expensive part: it needs a matte of the subject.

**Numbers that matter**
- 38 cuts in 31.5 s; median 0.71 s; **no hold longer than 2.4 s**.
- 6 blur-whips; **14/38 cuts land inside 80 ms of a kick** — this is the most
  beat-locked edit of the five.
- Type on screen 49% of runtime across 19 runs, many at full width.
- Grade is mid-dark, desaturated (0.37) so the type can carry the colour.

**What building it needs.** Either (a) subject mattes per shot, or (b) an honest
approximation: the same type at the same scale, *over* the picture with a
knockout/blend so it reads as behind. (b) gets the rhythm and 80% of the look
without a tracker. **Cost: high** if we do it properly, **low** if we do (b).

---

## 3. `square` — v12, "I lost Gwen"

**What it is.** 1:1, interview/documentary register. Long takes of people
talking, captions that are simply what they said — "I LOST GWEN", "MY…", "SHE
WAS", "I NEVER GONNA BE ABLE" — plain, centred, no styling. The cut lands where
the sentence lands.

**The invariant.** The edit does not perform. There are almost no cuts (14 in
30 s) and nearly half the runtime is in holds of 4 s or more. Type appears only
in the first 8 s and then stops entirely for the last 22 s. The frame is square.

**Numbers that matter**
- 14 cuts, median 1.33 s, longest 4.57 s, **44% of runtime in 4 s+ holds**.
- Type 16% of runtime, 4 runs only, then gone 22.2 s before the end.
- 3 blur-whips — and they are the only "edit-y" thing in the file.
- High saturation (0.61): the picture is left alone.

**The catch.** Square means cropping landscape footage. You said no vertical
crop; this is the same category of decision, so it is **your call, not mine**.

**What building it needs.** Square presentation, a plain centred caption engine,
a slow planner with a long-hold bias. **Cost: low.**

---

## 4. `hymn` — v13, "Sapne Sajaave"

**What it is.** Nearly black (median luma **11** — the darkest thing we have by
a factor of two), with two type voices at once: a **white serif** set in the
middle of the frame and a **yellow handwritten script** underneath it, sitting
slightly lower and to the right, as if written on after. It ends on a title card.

**The invariant.** Two voices, two colours, two positions, always paired — the
serif states the line, the script signs it. Type is on screen **69% of the
runtime**: this is a lyric video more than a montage. The grade crushes
everything to a near-black field with one warm light source, so the type is the
brightest thing in frame.

**Numbers that matter**
- 15 cuts, median 1.79 s — slow. No blur-whips at all.
- Only 2/15 cuts on a kick; the first 15.8 s has **no kicks at all** — the edit
  runs on pad/strings until the beat drops, then 22 kicks and 8 cuts.
- 8 type runs, one of them 6.8 s long (0.7–7.5 s).
- Ends on an endcard (last ~2.5 s).

**What building it needs.** A two-voice type engine (serif + script, fixed
offset), a crush-black grade preset, and endcard support. **Cost: medium** —
we have the fonts (`buttershine_serif.zip`, `couture-font.zip` etc.).

---

## 5. `barrage` — v26, the Marvel cut

**What it is.** The opposite pole to `cold_read`. Bright (median luma **85**,
the brightest of all), fast, and **14 blur-whips in 37 s** — a whip every 2.6 s.
52 cuts, median 0.53 s, and not one hold over 3.1 s.

**Read in full — `studio/reference/barrage_v26.md`.** After watching all 1,110
frames, three things corrected the fingerprint:

- **There is no lyric layer at all.** The "36% type" is branding: a
  `#PRINCEEDITS` watermark for the whole runtime, a burnt-in title for 2 s, a
  credit card at 2.83 s, a channel logo for the last 2.4 s. This style is music
  and picture only.
- **It has a breakdown.** Loudness sits at −10 dBFS but falls to **−33 at
  18.0 s**, under the Spider-Verse section, and to −32 at 26.0 s. The instrument
  said "0% silence" and was right; it still missed the structure.
- **The tour is the shape.** One hero per section — Cap, Thor, Iron Man,
  Spider-Man, Panther/Hawkeye/Miles, the Endgame fight, Strange — joined by hard
  cuts, entered and left by a three-frame flash or a whip. The longest shot is
  3.10 s and it sits **in the breakdown**, not at the end.

**The invariant.** Half-second cutting, flashes as punctuation, a quiet third in
the middle where one shot is allowed to hold, and no words on screen except the
signature. Bright, flat grade so the flashes read white.

**Numbers that matter**
- 52 cuts / 37.2 s, median 0.53 s. Six cuts are exactly **0.10 s — three frames**.
- 14 blur-whips, two of them long runs (3.3 s and 2.4 s).
- 16/52 cuts on a kick, median offset 0.144 s — the tightest of the five.
- Type: watermark only. Grade: luma 85, sat 0.33.

**What building it needs.** Pacing profile, flash-on-beat, whip as join *and*
texture, a breakdown window at ~65–70% where luma and cut rate both drop, cards
at both ends. **Cost: lowest.**

### Correction to the earlier note on v26
It is not a Powerpuff Girls promo — you confirmed that. The footage is Marvel and
the burnt-in title reads 無限轉場 ("infinite transitions"), so the file is a
transition showcase from a Chinese edit account, with that account's watermark
and endcard inside it. Two ownership layers are baked into the reference; ours go
where ours always go.

## What I propose to build, in this order

Cheapest and most reusable first, so the shelf fills fast and each one is
verified before the next starts:

1. **`barrage`** — pure pacing + whips + grade, all existing parts. Half a day.
2. **`square`** — needs your yes on the crop. Half a day.
3. **`cold_read`** — fragment captions + end hold. One day.
4. **`hymn`** — two-voice type, crush grade, endcard. Two days.
5. **`hype`** — needs a subject matte; I'd start with the approximation. Two days.

Each lands as `studio/stylepacks/<name>.json` plus, where needed, its own module.
**`house` is untouched throughout** — it stays the default and stays verified.

## The gate every new style must pass

Render a 30 s test from `footage/post2/`, run `studio/study` on it, and compare
against the reference's row above. Pass = within **±20%** on median shot length,
holds, whips and type share, and the grade land within a few points of luma. If
a style passes on one clip and fails on a different one, it was surface, not an
invariant — and it gets rebuilt.

## Choosing

    python -m studio.styles --list
    python -m studio.pipeline ... --style house     # what made Faahun, Zaalima, Stay
    python -m studio.pipeline ... --style barrage   # etc.

No `--style` still means `house`.
