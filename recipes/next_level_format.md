# Next-level format — teardown of the 4 reference shorts (2026-10-15)

Source: `references/next_level/` (copies; originals on `main` root:
`1000106089/1000107167/1000110841/1000113144.mp4`). All four carry a
Fiverr watermark — these are pro-editor outputs, i.e. the benchmark.

## Per-video teardown

### V1 `1000106089` — trading mindset (17.9 s, ~22 cuts)
- Talking head + word captions mixing TWO fonts: bold sans for speech,
  serif italic for feeling words ("Heard", "Every").
- Full-screen BLUE kinetic-type cards: the claim re-typeset as a poster
  ("Success is not just about HARD working") — small connectives float
  above the huge keyword, words stagger in.
- Stock B-roll of a stressed man; a MEME clip insert (Michael Scott:
  "it's the fight against…") as a pattern break.
- Cumulative numbered list burned in: "1 FIGHT YOUR EGO" then
  "+ 2 FIGHT YOUR DESIRES".

### V2 `1000107167` — home-buying finance (12.3 s, ~18 cuts)
- Hook question to camera, then WHITE-background infographic world:
  house photo card, big "10 Years" badge, an animated circular diagram
  (Budget→Income→Savings→Expenses drawing itself), STEP 2/3/4 pills.
- Small photo cards pinned over the speaker's chest (never the face).
- Clean brand blue throughout; captions small, accent keyword.

### V3 `1000110841` — roofing authority (30.1 s, ~24 cuts)
- Outdoor talking head, captions CENTER-frame in stacked red/white
  type ("BUT / UP CLOSE"), key word in red.
- Proof cards everywhere: rounded-corner photo cards (house, shingle
  close-ups) over blurred B-roll, red label chips ("EXPOSED ASPHALT"),
  5-star review screenshot cards, a map card, a countdown sticker
  ("THE WINDOW'S ALREADY CLOSE 00:02").
- Every claim gets a visual receipt within ~2 s of being spoken.

### V4 `1000113144` — AI-websites pitch (27.6 s, ~30 cuts)
- Bedroom talking head, captions as stacked posters over the chest
  ("NOBODY BELIEVES ME", small teal subline = the spoken filler).
- White flash cards: falling-money PNG animation, "$1.4 MILLION"
  counter sticker, "SELLING AI WEBSITES" logo lockup with an icon.
- A PERSISTENT proof sticker ("$20,000 CASH") stays on screen for
  ~8 s while he keeps talking — the number never leaves the eye.

## The shared DNA (what actually makes them engaging)

1. **A visual event every 1–2 s.** 18–30 cuts per clip; the frame is
   never allowed to sit still. Speaker → card → B-roll → sticker.
2. **Captions are graphic design, not subtitles.** Centre-frame
   stacked type, mixed fonts/sizes per word, connectives small,
   keywords huge in ONE brand accent. Face stays clear; text rides
   the chest.
3. **Claim cards.** Every few seconds the speech stops and the claim
   is re-shown as a full-screen kinetic-type poster. This is the
   retention engine: the video keeps re-hooking.
4. **Proof is shown, not said.** Photo cards with label chips, review
   cards, maps, counters — a receipt for every claim, on screen
   within seconds.
5. **Persistent stickers.** Numbers/steps stay pinned while talking
   continues; lists accumulate (1 → 1+2 → 1+2+3).
6. **Pattern-break inserts.** Meme clips, flash frames, falling money
   — one surprise per clip minimum.
7. **Sound:** constant music bed (all four ≈ −14 LUFS integrated,
   audible bed in every gap), punch transitions, voice on top.
8. **One brand system per creator:** one accent colour, one type
   pairing, logo-ish lockups. Instantly recognisable in a feed.

## Have vs gap (our engine today)

| DNA move | Status |
| --- | --- |
| True-sync word captions, keyword accent | ✅ have (bottom block style) |
| Hook headline (now typed + keystrokes) | ✅ have |
| Camera punches, continuous push, B-roll cutaways | ✅ have |
| Sound design, loudnorm, QC gate | ✅ have |
| Centre-frame POSTER captions (mixed font/size stack) | ❌ new layout mode |
| Full-screen kinetic CLAIM CARDS | ❌ new |
| Rounded-corner PROOF CARDS + label chips over blurred B-roll | ❌ new |
| Persistent STICKERS / accumulating lists / counters | ❌ new |
| Music bed + ducking | ❌ new (synthesize CC0 beds) |
| 1–2 s visual-event pacing planner | ❌ new (plan-level) |
| Animated diagrams (V2's budget wheel) | ⏸ later — PIL-drawn basics |

## Build plan (in order)

1. **`poster` caption mode** ✅ SHIPPED — centre-frame stacked type
   from the same true-sync words: keyword huge, connectives small
   (serif for pure-filler rows, DejaVu Serif), one accent. Stacks sit
   on the chest (`center_y` 0.66); QC face-check covers Poster events.
2. **Claim cards** ✅ SHIPPED — ASS-rendered full-screen brand panels,
   lines stagger in (`--card AT,DUR,LINE1,LINE2`), last line accented.
3. **Card inserts** ⏳ NEXT — image + label chip composited over a
   blurred frame (ffmpeg overlay), placed below the chin, face-checked.
4. **Stickers + lists** ✅ SHIPPED — persistent accent chips
   (`--sticker AT;DUR;TEXT;SUB;POS`) and accumulating numbered lists
   (`--list AT;DUR;A|B|C`) as long-duration ASS events.
5. **Music beds** ✅ SHIPPED — 3 synthesized loopable beds (dark /
   bright / chill, `assets/music/`, CC0) + `sidechaincompress`
   ducking under the voice (`--music MOOD`).
6. **Pacing planner + QC** ✅ QC SHIPPED — `visual_pacing` check (a
   visual event at least every 3.5 s) runs on every render; the
   planner itself is the agent's segment choice per clip.

First demo: `post6/` (MILK grading clip in the new format, QC PASS).

**Direction update:** this ASS-based format was the stepping stone.
The long-term system is the HTML/CSS motion-graphics layer in
`motion/` (frame-by-frame Chromium renders composited with ffmpeg —
see `motion/README.md`). Stage 1 (poster/chip/card/FX) is built and
QC-green on a 10 s demo (`motion/demo/`); stage 2 adds the
proof/PiP cards, B-roll windows, counters, lists and process graphics
from the table above, in that engine.

Hard rules that stay: never cover the face (cards sit below the chin,
QC-verified), captions = exactly what was said, assets licensed/CC0
(no ripped meme clips — we generate or use campaign-supplied media).
