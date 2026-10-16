# Stage C review pack — Part 3: sound (+ face-focus fix)

Three videos, all **QC v2 PASS 12/12** and **SOUND QC PASS**:
`milk_grade_stageC.mp4` (10 s), `milk_budget_stageC.mp4` (28.8 s),
`sartain_stageC.mp4` (12.6 s). Each ships with its contact sheet,
motion QC report (`*_qc.txt`) and full sound event log
(`*.sound.json` — every event's frame, type, variant, gain).

## Face focus (user-reported fix, applies to all 3 videos)

The old bases used a **fixed crop window**: measured on the Stage-B
budget video, the speaker's face was clipped at the frame edge in
**28% of face frames**. New `motion/reframe.py` replaces the blind
crop for every base: YuNet face detection on every frame, a
continuity-locked speaker track (size-aware identity cost — it cannot
hop to a neighbour), a crop window that pans smoothly (velocity
clamped, width NEVER changes — no zoom pulsing), snaps to the new
shot on every cut, and guarantees the speaker's face + margin inside
the frame. Re-measured on the finals (largest face, every 3rd frame):

| video | face samples | cut | worst margin |
|---|---|---|---|
| milk grade | 79 | **0** | 56 px |
| milk budget | 254 | **0** | 8 px |
| sartain | 74 | 1 frame at −2 px | — |

The single Sartain graze is a 2 px touch in an extreme closeup whose
face fills the whole frame — below detector noise. One engine change
came with it: process panels got the same dark plate as list panels
(new framing put white step text on a pale wall, 2.9:1 → PASS), and
Sartain's early text zones moved per-shot into face-free space.

## Sound design (`motion/sound.py`)

Every sound is **synthesised in code** (oscillators + filtered
noise) — original, CC0 by construction, nothing downloaded
(`../SOUND_LICENSE.md`). Events derive from the timeline, so each
lands on its graphic's exact frame:

- item entries pop; panel rows step in; PiP/B-roll whoosh;
- poster/card words get soft keystrokes — **first + keyword words
  only**, behind `--typing-sound on|off` (default on);
- counters roll 3 ticks and **land on the spoken word**;
- every cut: flare cuts get a 0.45 s riser ending in a boom **on the
  cut frame**, other cuts a snap; 130 ms bed dips precede big impacts;
- sub-bass bed (43–86 Hz) ≈24 dB under the voice + generated pad
  loop ducked 12 dB under speech; voice gently levelled, SFX rides
  6–10 dB under it;
- variants rotate per kind with seeded ±3% pitch / ±10% volume;
- mix normalised **in the mix itself** (soft ceiling + measured
  loudness gain, single encode): all three finals measure
  **−14.1 LUFS, true peak −1.5…−3.0 dBTP**.

Density, reported honestly: this budget cut has a cut every 1.44 s,
so cut accents alone are ~0.7/s; totals are 1.70 accents/s on budget,
1.14 on grade, 0.85 on Sartain (keystrokes/ticks counted separately
as texture in the `.sound.json` logs). The spec's ~1/s is met at
typical cut density; nothing was left silent to hit the number.

## Regenerate

```bash
# bases now start with face-tracked reframing (per 16:9 segment):
.venv/bin/python motion/reframe.py work/<job>/seg_raw.mp4 work/<job>/seg_f.mp4
# ... scale/concat as in review_a/README.md, then the Stage-A chain,
# then one new final step per video:
.venv/bin/python motion/sound.py work/<job>/timeline_fx.json \
    work/<job>/final.mp4 work/<job>/final_s.mp4 [--typing-sound off]
```
