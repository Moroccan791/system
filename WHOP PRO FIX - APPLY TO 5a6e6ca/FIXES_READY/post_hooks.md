# Best hooks to keep viewers (Street — apply to post4-7 first)

**Current problem:** You start where she starts talking. Viewer has no reason to stay.

**Fix: Cold-open payoff card 0.0-1.2s BEFORE face.** All 4 below use your existing accent colors + whop editorial style (no new assets).

### Post4 (Terrified) — use stage card as HOOK not mid
- **0.0-1.2s:** `I DIDN'T WANT TO GO ON STAGE` (your stage vector, but keep face 20% visible behind with blurpad, not full navy cutaway)
- **1.2s:** hard cut to face `You know, they're gonna write online,` — keeps tension: *what happened on stage?*

### Post5 (Worth) — WORTH as face overlay not black cut
- **0.0-1.2s:** Face on, text stacked on chest: `MY WORTH ISN'T IN MY BODY` where `WORTH` is displaybook 140px teal #14E5C5, rest regular 78px white. Face visible behind.
- End with 2s question card: `What is your worth in?` — drives comments.

### Post6 (Oak Tree) — OAK TREE at 0s not 3s
- **0.0-1.2s:** `OAK TREE` huge white + sage #78A974 line (your existing card, just move to front)
- **1.2s:** face `I'm trying to build that will shade...` where `build`/`protect` sage italic as you already do (this is your best keyword treatment — keep)
- Merge `image` orphan: `that will shade and protect my image` one cue.

### Post7 (Door) — DOOR payoff first
- **0.0-1.2s:** `SHE OPENED THE DOOR FOR HER MOM` (door vector if you have it, else text)
- Fix `angry`: move from corner tiny red to inline `I will never be angry` where `angry` is serifbi red #C7654E on same line.

### How to make in motion/
Each hook is a `poster` motion with `at:0.0 until:1.2`:
```json
{"type":"poster","kind":"hero","text":"OAK TREE","accent":"#78A974","at":0.0,"until":1.2}
```
Then face captions start at 1.2s. No extra render time — it's one more poster in timeline.

Test order: post6 (closest to template) → post5 (short fix) → post4 → post7. Post2/3 are good, just add 1 keyword pop each.
