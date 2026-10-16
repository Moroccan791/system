# MOTIONS.md — the motion library

Every graphic this system can put on screen, what each one is FOR, and the
rules for choosing. A motion is not decoration: it exists to do one of six
jobs for the viewer. If a graphic does none of them, it does not go in.

Built as class presets (vector scenes + typographic components) rendered by
`motion/stage.html` — never AI-generated imagery. Generated pictures are a
fallback for concrete b-roll only, always labelled ILLUSTRATIVE, never
presented as proof.

## The six jobs

| Job | What the viewer gains | Typical motions |
|---|---|---|
| **SHOW** | Sees something words alone can't carry — a quantity, a shape, a structure | people, bars, line, stack, donut, pip/broll, process |
| **PROVE** | Evidence: the exact words, the real number, the source | quote, counter, card (verbatim lines) |
| **COMPARE** | Two things side by side; the difference is the point | versus, bars (hot bar), stack |
| **ORIENT** | Knows where we are: in a list, in a process, in time | list, process, timeline, chip |
| **EMPHASISE** | Feels the weight of one word or claim | poster, card, counter (punch number), neon word, fx hit |
| **FEEL** | Mood and cinema: transitions, light, sound, space | fx (flare/leak/opening), broll cutaways, grade, whoosh/hit |

## Governing rules (apply to every video)

1. **Face-time allocation comes first.** If a campaign requires the featured
   person on screen for ≥ X% of the clip (e.g. Michael Sartain ≥ 50%), plan
   the timeline to that ratio: full-bleed graphics count against face time,
   card-mode graphics and typography over the speaker do not. With no such
   rule, lean on motion graphics to draw and hold attention — but the speaker
   still owns the hook and the payoff.
2. **One idea per screen.** A graphic shows one number, one comparison, one
   list. Two ideas = two graphics, in sequence.
3. **Never the same motion twice in a row.** Alternate families (data →
   typography → person → data). Repetition reads as a template; variety
   reads as editing.
4. **Captions never stop.** The caption layer runs under everything; a
   full-bleed scene is a cutaway, not a caption break.
5. **A graphic must change or leave.** Dwell caps are enforced by
   `motion/validate.py`: general ≤ 3.0s; full-bleed metaphor scenes
   1.0–1.8s; full-bleed data scenes 1.2–2.5s (they are still moving).
   Cadence: picture inserts (PiP/B-roll/metaphor scenes) ≥ 6s apart;
   full-bleed data scenes ≥ 2.4s apart, so an MG-led stretch can chain
   scenes without ever crowding. In practice chain data scenes
   2.4–2.5s start-to-start: QC pacing also caps the gap from any item's
   start to the next visual change at 2.5s.
6. **Honest data only.** Charts show real numbers from the speech or the
   source. No on-screen ILLUSTRATIVE tags on data scenes (decided
   2026-10-16) — instead, anchor every value to something actually said
   ("57 in the chat, all of them awake, none stepped in"). A scene may
   visualise the speaker's argument, but never present an invented
   statistic as a measured fact to make a prettier chart.
7. **Brand lock.** One accent colour + black/white (or the client's brand
   colours) per video. Data scenes use the accent for the ONE thing that
   matters (the hot bar, the winner, the counted people) and steel greys for
   everything else.
8. **Sound follows motion.** Entries land with a soft hit/whoosh; counters
   tick; nothing moves in silence at a key moment. Typing clicks only on
   headlines/key words (see FEATURES.md).
9. **No graphic over a speaking face.** Full-bleed = full cutaway. Card-mode
   vehicles and typography live in the caption-safe zones (QC face-zone
   rules apply).
10. **Choose by the sentence, not by taste.** Use the choosing table below;
    if two motions fit, prefer the one not used most recently in this video.

## Choosing table — hear this, show that

| In the speech… | Motion | Job |
|---|---|---|
| A number or % lands ("57 men", "90%") | counter (punch) or people/bars if it's a quantity of things | PROVE / SHOW |
| "N men / people / users…" (a crowd quantity) | **people** pictogram grid | SHOW |
| Several quantities compared ("A got 10, B got 40") | **bars** with `hot` on the point | COMPARE |
| Change over time ("kept growing", "over 6 months") | **line** | SHOW |
| A split of a whole ("most of them…", "70/30") | **stack** or donut | SHOW / COMPARE |
| This vs that, winner/loser | **versus** | COMPARE |
| A sequence in time ("first… then… by Friday") | **timeline** | ORIENT |
| A process / steps explained | process (step stack) or timeline | ORIENT / SHOW |
| First / second / third… | list plates | ORIENT |
| Exact words matter ("she literally said…") | **quote** (verbatim only) | PROVE |
| A strong claim, the thesis of the clip | card (≤3 lines) or poster | EMPHASISE |
| One emotional word | poster with neon/serif word, fx flare | EMPHASISE / FEEL |
| It happened over text ("group chat", "she texted…") | **chat** bubbles filling a phone | SHOW |
| A circle / network / team ("his circle", "connections") | **network** nodes linking to a hub | SHOW |
| Intensity or certainty ("100%", "how serious", effort) | **gauge** needle sweep | SHOW / EMPHASISE |
| A named place anchors the story ("at Cornell", "in Miami") | **map** pin drop | ORIENT / SHOW |
| A day is named ("on Friday…", deadlines) | **calendar** (day lights up) | ORIENT |
| A time is named ("by 7:30", "20 minutes") | **clock** (hands sweep) | ORIENT |
| Money lands ("costs $500", "the price…") | **price** tag | SHOW |
| Rules / habit steps ("text first, wait a day…") | **checklist** ticking off | SHOW |
| Attraction, being drawn in ("she's drawn to…") | **magnet** | SHOW / FEEL |
| Filter / drop-off ("out of 100, only 7…") | **funnel** | PROVE |
| Hierarchy / tiers ("top 1%", "levels") | **pyramid** | SHOW |
| An aim is stated ("the goal is…", "focus on…") | **target** | EMPHASISE |
| Rank / best ("number one", "the best") | **podium** | PROVE |
| Transformation ("I was shy, now I'm bold") | **beforeafter** | COMPARE |
| Advantages weighed against downsides | **proscons** | COMPARE |
| Energy level ("drained", "fully charged") | **battery** | FEEL |
| A series part begins ("part two…") | **chapter** marker | ORIENT |
| One word IS the clip ("…exactly.") | **bigword** | EMPHASISE |
| Warning ("never do this", "big mistake") | **alert** | EMPHASISE |
| Feelings land ("I actually loved her") | **heart** | FEEL |
| A concrete picturable noun | pip / broll (client footage first) | SHOW |
| Scene change, breath, mood | fx leak/flare, broll cutaway | FEEL |

## The library

### Data scenes (`"type": "vector"`, SVG, animated)

All take `"mode": "fullbleed"` (cutaway) or `"mode": "card"` (panel over the
speaker), plus `"label"` (kicker) and `"sub"`. Data-scene examples use the
campaign accent for the point that matters.

#### people — SHOW a quantity of people
A pictogram grid of person icons fills in stagger; the big number counts
with the fill. Grey icons beyond `count` (up to `total`) show "of how many".
```json
{"type":"vector","name":"people","mode":"fullbleed","label":"IN THE GROUP CHAT",
 "count":57,"total":100,"at":8.20,"until":10.60}
```
Params: `count` 1–100 (required), `total` ≤100, `cols` 5–20 (default 10).
Use when the crowd IS the story. dwell 2.0–2.5s for large counts.

#### bars — COMPARE quantities
Bars grow staggered; values count up sitting on the bar tips; the `hot`
index takes the accent.
```json
{"type":"vector","name":"bars","mode":"fullbleed","label":"REPLIES PER DAY",
 "values":[12,47,9],"labels":["HIM","HER EX","YOU"],"hot":1,"at":12.0,"until":14.2}
```
Params: `values` 2–7 (numbers), `labels` ≤12 chars each, `hot` index.

#### line — SHOW change over time
A line draws itself left→right; points pop as it passes; the final value
counts up at the end.
```json
{"type":"vector","name":"line","mode":"fullbleed","label":"MESSAGES / WEEK",
 "points":[4,14,11,33,58],"unit":"","at":16.0,"until":18.3}
```
Params: `points` 2–8 values 0–100, `unit` suffix (≤4 chars, e.g. `"%"`, `"K"`).

#### versus — COMPARE two sides
Two panels slide in from opposite sides; both numbers count; the `win`
side gets the accent border/fill; a VS badge pops between them.
```json
{"type":"vector","name":"versus","mode":"fullbleed","label":"WHO TEXTED FIRST",
 "left":{"label":"WAITED","value":21},"right":{"label":"DIDN'T","value":3},
 "win":"left","at":20.0,"until":22.2}
```
Params: `left`/`right` {label ≤16 chars, value}, `win` optional, `unit`.

#### stack — SHOW a split of a whole
A 100% bar fills segment by segment; % counts under the bar, names above.
```json
{"type":"vector","name":"stack","mode":"fullbleed","label":"THE GROUP CHAT",
 "parts":[63,37],"labels":["MEN","WOMEN"],"at":24.0,"until":26.2}
```
Params: `parts` 2–4 numbers (normalised to 100%), `labels`.

#### timeline — ORIENT in time
A line draws across; dated events pop as it reaches them (labels alternate
above/below; `sub` = the date/beat in accent).
```json
{"type":"vector","name":"timeline","mode":"fullbleed","label":"HOW IT PLAYED OUT",
 "events":[{"x":0.05,"label":"MET","sub":"DAY 1"},{"x":0.5,"label":"GROUP CHAT","sub":"WEEK 2"},{"x":0.95,"label":"EXPOSED","sub":"FRIDAY"}],
 "at":28.0,"until":30.3}
```
Params: `events` 2–5, `x` = 0–1 position along the line.

#### quote — PROVE with their exact words
Giant accent quote mark; lines rise in one by one; attribution last.
Verbatim quotes only — never paraphrase inside a quote graphic.
```json
{"type":"vector","name":"quote","mode":"fullbleed",
 "quoteLines":["I never said","that to him."],"by":"Her message, read on the show",
 "at":32.0,"until":34.4}
```
Params: `quoteLines` 1–3 lines ≤30 chars, `by` attribution ≤40 chars.

#### chat — SHOW the conversation itself
A phone frame fills with message bubbles, staggered as if being sent.
The motion for anything that happened over text: group chats, DMs, "she
texted…", reply counts. Bubble texts must be what was actually sent (or
clearly the words being quoted) — never invented dialogue presented as
real messages.
```json
{"type":"vector","name":"chat","mode":"fullbleed","title":"GROUP CHAT",
 "messages":[{"text":"did you see her story?","me":false},{"text":"1","me":false},{"text":"1","me":true}],
 "label":"57 MEN IN THE GROUP CHAT","at":20.85,"until":23.05}
```
Params: `messages` 2–6 {text ≤30 chars, me = accent/right side}, `title`.

#### network — SHOW a circle / web of people
A centre node (the person) with satellites linking in one by one. For
networking, circles, teams, "everyone he knows", org structures.
```json
{"type":"vector","name":"network","mode":"fullbleed","title":"YOU",
 "count":8,"label":"HIS CIRCLE","at":12.0,"until":14.2}
```
Params: `count` 3–14 satellites, `title` = hub text (≤6 chars).

#### gauge — SHOW intensity / certainty / a level
A semicircular gauge sweeps its needle to the value while the % counts.
For "a hundred percent", confidence, seriousness, effort — one number
with weight, where a plain counter would feel flat.
```json
{"type":"vector","name":"gauge","mode":"fullbleed","value":100,
 "label":"SHOULD SOMEONE HAVE ACTED?","at":28.2,"until":30.4}
```
Params: `value` 0–100.

#### map — SHOW where it happened
A street-grid card; a pin drops with pulsing rings on the named place.
For named places that anchor the story (a campus, a city, a venue).
Stylised map — it shows *where*, never fake geography detail.
```json
{"type":"vector","name":"map","mode":"fullbleed","place":"CORNELL",
 "label":"WHERE IT HAPPENED","x":0.52,"y":0.44,"at":4.0,"until":6.2}
```
Params: `place` ≤24 chars, `x`/`y` = pin position 0–1 inside the card.

#### donut — SHOW one share (existing)
Ring sweeps to a %; centre number counts. `value` = percent.
Use for a single dominant share; use stack when the split itself compares.

#### arrow — SHOW direction/growth (existing)
Self-drawing arrow; metaphor for rise/fall/momentum. Keep abstract —
never draw a data claim with it (use line for real change).

#### led — SHOW a panel/board filling (existing)
Grid of cells lighting up; good for "slots filled / spots taken" metaphors.

#### hoop — FEEL/EMPHASISE a score moment (existing)
Basketball shot arc; playful payoff visual for "he scored / she shot her
shot" beats in dating content. Metaphor, never data.

#### burst — FEEL impact (existing)
Radial burst on a hit word; pairs with the sound hit. 1.0–1.8s full-bleed.

#### calendar — ORIENT in the week
Seven day cells pop in; the spoken day (`day` 0=Mon) lights accent and
rings. Use when a day/date carries the point ("by Friday…").

#### clock — ORIENT in the day
Clock face; hands sweep (`sweep` turns of the minute hand) while
`title` names the spoken time ("7:30 AM"). Use for stated times and
deadlines.

#### price — SHOW a cost
A price tag swings in on its string; the amount counts onto it
(`value`, `prefix` "$", `decimals`). Money context beats a bare
counter — assign.py routes $ numbers here.

#### checklist — SHOW rules/steps
Rows (2–5 `entries`) tick themselves off one by one. For rules,
habits, "do this, then this" — the ticks ARE the process.

#### magnet — SHOW attraction
A horseshoe magnet; filings fly in and stick (`count` dots). The
dating-content metaphor for attraction/draw — abstract, never data.

#### funnel — PROVE drop-off
`from` count at the top, dots fall through, `to` counts out at the
bottom. For filters, funnels, "out of 100, only 7…".

#### pyramid — SHOW hierarchy
Three levels stack (bottom first); the TOP level is the accent
(`labels` = [top, mid, base]). Hierarchies, tiers, "top 1%".

#### target — EMPHASISE an aim
Concentric rings; an arrow strikes the centre and pulses. Goals,
focus, "the whole point is…".

#### podium — PROVE rank
Blocks rise: sides first, the winner (centre, accent) last.
`labels` are ordered [2nd, 1st, 3rd] to match the blocks. Rankings,
"number one", best-of lists.

#### beforeafter — COMPARE transformation
Muted BEFORE panel slides in, accent AFTER answers it (`before`,
`after` short words). Transformations, glow-ups, then-vs-now.

#### battery — FEEL energy
Charge bar fills to `value` % with a counting readout. Energy,
motivation, "running on empty" — the level is the spoken claim;
anchor it to the words (drained ≈ low, charged ≈ high).

#### proscons — COMPARE sides
Two columns land alternately: accent ✓ (`pros`) against muted ✕
(`cons`), ≤4 each (column heads from `labels` [pros, cons]). For
weighing, trade-offs, "good news / bad news".

#### chapter — ORIENT structure
PART `index` marker with progress dots (`total`) and a `title`.
Reusable series furniture for multipart content — not a scene for
mid-sentence beats.

#### bigword — EMPHASISE one word
A single payoff `word` takes the whole frame, accent underline
sweeps under it. The heaviest typographic hit we have; one per clip
is plenty (pair with the sound impact).

#### heart — FEEL
A heart beats (pulse-synced rings) for the emotional beat. Love,
feelings, "it got real". Metaphor only.

#### alert — EMPHASISE a warning
Warning triangle lands with a shake and settles. Mistakes, dangers,
"never do this". Use sparingly — it shouts.

### Typography (over the speaker; does not cost face time)

#### poster — EMPHASISE the spoken words
2–4-word chunks of the actual speech, huge, lower-third zone; key word in
accent (kind `key`), emotional word neon (`neon`), soft/reflective words
serif italic (`serif`). This is the system's backbone — most sentences live
here. Words appear on their real spoken onsets.

#### card — EMPHASISE a thesis / PROVE a verbatim line
Full statement card, ≤3 lines, ≤5 words/line, words pop on onsets. Use for
the clip's thesis, the hook restated, or the payoff. Never paraphrase a
quote into a card and call it a quote — that's `quote`'s job, verbatim.

#### counter — PROVE a number
One number counts up 0→value fast (0.8–1.0s) with a label. For a lone
statistic. If the number is a crowd or has company, prefer people/bars.

#### chip — ORIENT with a kicker
Single-line label bar (chapter/section marker, "THE RULE:", a name+role).
One line only, no sub (validator enforces).

#### list — ORIENT through an enumeration
Numbered plates slide in on each spoken item ("first… second… third…").
Plate text = the item, not a summary of the whole sentence.

#### process — ORIENT through steps
Step stack for how-to/mechanism ("step 1… then… finally…").

### Picture (cutaways; cost face time)

#### pip — SHOW a concrete thing, small
Picture-in-picture panel (w 0.55–0.70 of frame). Client/product footage
first; generated image only if nothing real exists, labelled ILLUSTRATIVE.

#### broll — SHOW/FEEL at full frame
Full-screen cutaway 1.0–1.8s. Real footage > generated. Use to break a
long talking stretch every 4–6s when the speech names something visible.

### fx — FEEL (transitions & hits)
`flash` (cut punctuation), `flare`/`leak` (light, mood, scene change),
`opening` (first-frame energy), `bwflash` (shock/reversal beat). 6–10
frames only; an fx is a comma, not a sentence.

## Blending rules — how motions join the video (never random)

A motion graphic earns its place by being *called for* by the speech.
`motion/assign.py` scans the timed transcript and proposes a motion for
every spoken trigger, each with its anchor word and reason recorded;
the author confirms, fills creative params, or rejects. What survives
that pass obeys these rules:

1. **Anchor to the trigger word.** A scene enters on (or just before)
   the word that calls for it: counters start their roll ~0.9s early so
   they *land* on the number; a chat scene opens as "group chat" is
   said. A graphic that floats free of any spoken anchor is decoration
   — cut it.
2. **Internal sync.** The graphic's payoff lands with the phrase, not
   after it: the people grid finishes filling as the count is spoken,
   the gauge needle settles on "percent", the last chat bubble arrives
   with the last quoted message.
3. **One motion per beat, strongest beat wins.** If a sentence triggers
   two candidates, the one matching its main clause takes the screen;
   the other stays a poster. Hook and payoff beats outrank mid-clip
   beats when the face budget forces a choice.
4. **Rhythm is law.** A visual change every 1.5–2.5s (QC pacing cap).
   Full-bleed data scenes chain 2.4–2.5s start-to-start in MG-led
   stretches, or separate with poster beats between them. Never park a
   finished graphic on screen — it changes or leaves.
5. **Alternate families.** Data → typography → person → place:
   consecutive graphics come from different families so the eye keeps
   getting a new kind of picture (and never the same scene twice in a
   row — the validator enforces it).
6. **Face budget first.** Campaign minimum (e.g. Sartain ≥50%) caps
   total full-bleed seconds before any scene is placed; typography,
   counters and card-mode panels don't spend it. `assign.py` proposals
   are trimmed to the budget, strongest beats first.
7. **Blend, don't paste.** Entries land on word onsets and exits land
   as the sentence resolves — never mid-word into a new face shot for
   no reason. Scale, colour and motion language stay inside the
   video's one accent + brand lock, so a graphic feels shot *in* the
   video, not dropped on it.
8. **The window IS the beat (timing law).** A scene starts on its
   trigger word and is gone within ~0.3s of the spoken beat ending.
   A scene that outlives its beat does double damage: viewers feel it
   "hang", and the next sentence's words fall inside its window and
   are never captioned. Audit after authoring: every transcript word
   must appear in a poster, belong to a scene's own beat, or be
   covered by a counter — nothing else may go missing.
9. **Short beat → lighter form.** If the spoken phrase is shorter
   than the full-bleed minimum dwell (1.2s), do not stretch the scene
   to satisfy the dwell rule. Use the card form (scene rides above
   the caption zone, captions keep flowing, face stays) or a counter.
   The same applies when two beats land back-to-back: one takes the
   full frame, the other takes the card — never leave the 2.4s
   full-bleed spacing to chance.

## Applying the library (workflow)

1. **Purpose pass.** Run `motion/assign.py` on the timed transcript: it
   proposes a motion per spoken trigger (number, crowd, chat, place,
   certainty…) with the anchor word recorded. Read the transcript once,
   marking each sentence with a job (SHOW/PROVE/COMPARE/ORIENT/
   EMPHASISE/FEEL); confirm, fill, or reject each proposal. No trigger
   and no mark = poster only.
2. **Face-time budget.** Campaign minimum → cap full-bleed seconds
   (data scenes + broll + pip) at (100 − X)% of runtime; fill the rest
   with typography over the speaker.
3. **Assign from the choosing table**, honouring "never same twice in a
   row" and the dwell caps. Everything else stays poster captions.
4. Author the timeline JSON → `validate.py` → render → QC. Eyeball one
   frame inside every new scene before shipping (a scene you haven't seen
   is a scene that isn't done).

## Demo

`motion/timelines/motions_demo.json` — the M2 "57 men" clip re-cut with the
library attached: counter hook → people (the 57) → quote (his exact words) →
versus → bars → line → stack → timeline, posters elsewhere; scenes that
visualise his argument use only numbers his argument actually states.
with the standard `motion/produce.py` pipeline: **QC v2 PASS + SOUND QC
PASS at level 0** (−14.1 LUFS), shipped as
`motion/demo_library/motions_demo.mp4`. Speaker still holds ~55% of the
runtime — inside the Sartain ≥50% face rule even in this MG-dense cut.

---
*Library v1 — seven data scenes (people, bars, line, versus, stack,
timeline, quote) + donut/arrow/led/hoop/burst + the typography, picture and
fx components above. Add new motions here first (name, job, when-to-use,
JSON, params), then in `stage.html` (build + animate branch), the
`validate.py` whitelist and `schema.json` — in that order.*
