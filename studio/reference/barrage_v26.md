# v26 — the `barrage` reference, watched frame by frame

Source file: `.cache/refs/v26.mp4` — 1280×718, 30 fps, 37.17 s, 1,110 frames.
53 shots. This page is a full pass: every shot opened at two points, every
transition checked, audio envelope read at 0.5 s resolution.

---

## What actually happens

It is a **character tour**, not a single scene. Roughly one hero per section,
cut hard, with the music carrying the joins. Nine sections:

| time | section | what is on screen |
|---|---|---|
| 0.00 – 2.83 | **Captain America** | elevator / corridor fight — Cap front-on, then over the shoulder into a corridor of guards, then a spin with the shield. A burnt-in Chinese title reads **無限轉場** ("infinite transitions") across the first ~2 s. |
| 2.83 – 3.40 | **credit card** | pure black, small white text: *edited by 混剪团*. 0.57 s. It is not a beat — it lands mid-phrase. |
| 3.40 – 7.37 | **Thor / Cap** | Cap falling through lightning; Cap knocked down; then Thor, lightning crawling over him, eyes lit, then leaping. |
| 7.37 – 7.53 | black | 0.17 s — a breath, the only true black in the body of the edit. |
| 7.53 – 11.37 | **Iron Man** | helmet flying at the lens, hall of armour, snow landing, a warm gold flash that swallows the frame, then lifting off. |
| 11.37 – 12.23 | sky | two objects falling, wide, almost empty. |
| 12.23 – 13.87 | **Spider-Man** | falling through rubble, landing hard — five shots in 1.6 s, most under 0.3 s. |
| 13.87 – 16.90 | **Black Panther → Hawkeye → Miles** | Panther leaping through sky; Hawkeye drawing and firing (the release is a 0.10 s shot); Hawkeye inside the ship; a 0.10 s Iron Man; then Miles in the hoodie and the Spider-Verse glitch. |
| 16.93 – 25.87 | **the breakdown** | *This is the structural centrepiece.* A 1.6 s shot of Miles swinging down a magenta-lit street, then — at 18.93 — the **longest shot in the file, 3.10 s**, of Spider-Man in a subway car full of people, resolving into a blue explosion of web/energy. Then a 1.97 s warehouse fight, a hard whip at 24.0, and Endgame: Cap with shield and Mjolnir, the three of them charging. |
| 25.87 – 34.77 | **the fight** | Cap with the hammer, Thor vs Thanos in white energy, Spider-Man flipping in blue web, a street fight, Punisher, Thanos, Punisher again, Thor wreathed in lightning, Doctor Strange in the street and casting. |
| 34.77 – 37.17 | **endcard** | black, then a channel logo card (了不起的混剪团) plus a Douyin search bar. 2.40 s. |

---

## What the instrument could not see, and got wrong

Three things I had to fix by looking:

1. **There is no lyric layer.** The 36% "type on screen" I reported is not
   text design — it is **branding**: a `#PRINCEEDITS` watermark, top-right, for
   all 37 s; the burnt-in title for the first 2 s; the credit card at 2.83; the
   channel endcard for the last 2.4 s. **Not one lyric, not one word of
   dialogue.** `barrage` is a montage driven by music alone.
2. **The quiet part is the point.** The audio sits at −10 dBFS almost the whole
   way — but drops to **−33 dBFS at 18.0 s**, exactly under the Spider-Verse
   section, and again to −32 at 26.0 s. The instrument reported "0% silence" and
   was technically right; musically it missed that the edit has a **breakdown**.
3. **The longest shot is not an ending hold.** It is the 3.10 s subway shot at
   18.93 s, in the quiet section. The file ends with 2.4 s of logo, not footage.

## The transitions, precisely

- **52 cuts**, median shot **0.53 s**. Six of them are **0.10 s — three frames**:
  5.37, 9.77, 15.40, 16.20, 24.00, 26.83. Those are flashes, and they sit exactly
  on the beat. A flash of Thor, a flash of white, a flash of a bow release.
- **14 blur-whips**, and they are not all short: 17.27–20.57 is a **3.3-second**
  continuous blur run, and 12.4–14.8 is a 2.4 s bright smear. The whips are the
  *texture* of the middle, not just the joins.
- Cuts land on kicks **16 times in 52** with a median offset of 0.144 s — the
  tightest of the five references. Kicks run at a **0.35 s grid (~171 BPM as
  eighths, so 85.5 BPM in quarters)**.
- Four frames correlate almost perfectly with the *inverted* previous frame —
  2.87, 16.87, 25.90, 34.80. Those are the black cuts: the frame goes dark enough
  that the inversion test fires. They mark the section boundaries.

## The invariants — what survives a change of footage

1. **One hero per section, joined by hard cuts, entered and left by a flash or a
   whip.** The subjects change; the grammar does not.
2. **Median shot half a second.** If a cut survives 1.5 s it is a deliberate
   breath, and there are only a handful.
3. **A breakdown two-thirds in**, where the cutting stops, the loudness falls
   away, and the single longest shot holds the centre of the film.
4. **Nothing is captioned.** The music does the talking; the only text is
   ownership.
5. **Bright and flat.** Median luma 85, saturation 0.33 — the grade is lifted so
   the flashes read as white rather than grey.
6. **A card at the top and a card at the bottom** — credit in, logo out.

## What building `barrage` needs

Pacing profile (median 0.5 s, no holds outside the breakdown), flash-on-beat
(3 frames), whip as both join and texture, a breakdown window at ~65–70% where
luma and cut rate both drop, and a card system at both ends. Everything except
the breakdown window already exists in `studio/fx.py` and the planner.
**Cost: low.** It is the cheapest of the five and the best first build.

---

Contact sheets: `work/study/v26_shots_1..5.jpg`, `v26_mid.jpg`, `v26_tail.jpg`,
`v26_open.jpg`, `v26_whip.jpg`.
