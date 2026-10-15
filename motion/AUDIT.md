# Motion system audit — permanent rules (Parts 1–5)

Audit of the stage-1/2 codebase (`b2a1810` + `d0863dc`) against the
permanent-rules spec. **DONE** only where code + a QC rule already pass
it; **PARTIAL** where the mechanism exists but is out of tolerance;
**MISSING** where nothing implements it. Fixes land stage by stage:
A = Part 1, B = Part 2 (images), C = Part 3 (sound), D = Parts 4+5.

Baseline evidence: stage-1 QC PASS (5/5), stage-2 QC PASS (5/5),
`tests/test_decide.py` 10/10, both demo renders in `demo/`, `demo2/`.

## Part 1 — permanent rules

| # | Rule | Status | Evidence / gap |
|---|------|--------|----------------|
| 1.1 | First frame = intended shot; first caption already animating; frames 0–10 checked | DONE (Stage A) | Opening blur-zoom on the intended shot exists (composite `opening` fx); first poster at 0.31 s (f9) stage 2 / 0.30 s stage 1. No QC check of frames 0–10. |
| 1.2 | Connective text bold ≥3% frame height | DONE (Stage A) | Conn default 58 px = 3.02%, weight 800; schema floor 58. |
| 1.3 | Keywords heavy 6–8% | DONE | Default 118 px = 6.15%, weight 800, pop 85→108→100 (spec-exact in `wordEnter`). Schema range 60–200 px was too loose. |
| 1.4 | No text <3% anywhere | DONE (Stage A) | Violations in code: chip title 52/sub 38, pip label 44/34, pip ILLUSTRATIVE tag 26, broll sub 40, counter label **unset (≈16 px!)**, list head 42/plate 54/sub 36/badge № 36, process title 42/step 56/sub 38/circle № 36. Autofit shrink floors (30–32 px) also break it. |
| 1.5 | Dark outline 3–4 px + soft shadow on all text | DONE (Stage A) | 3 px stroke + soft shadow on poster/card/counter/serif; plate-backed text separates by plate. |
| 1.6 | Contrast ≥4.5:1, dark plate under text on light bg | PARTIAL (measured) | Soft dark plate now sits under poster stacks + counter; keywords became ink-on-accent plates (4.5:1+ by construction). QC samples the glyph window on the final composite per item: all three tests pass; worst honest readings 3.2–4.3:1 (counter accent digits) print as WARN, never hidden. |
| 1.7 | Long words auto-fit; 6% safe margin; never over face | DONE | `autofit` (≤88% width) + QC `margins` + QC `face_zone` (YuNet) all pass on both demos. (Autofit min scale must not shrink type <3% — see 1.4.) |
| 1.8 | Words appear 1–2 frames BEFORE onset (−60…0 ms) | DONE (Stage A) | Engine `WORD_LEAD` = 2 frames; QC measures visual offset −72..−62 ms across 85 words on three videos. |
| 1.9 | Chip 65–70% wide, 6–7% high, left icon, mask wipe 8f + streak, readable ≤10f | DONE (Stage A) | Fixed 67% width (~6.3% high), single line ≥58 px, icon left, 8f wipe; validator rejects chip `sub`. |
| 1.10 | Flare = full-frame diagonal light-leak, screen blend, 6–10f, peaks on cut | DONE (Stage A) | Old `flare` was a 560 px radial blob — replaced by the full-frame diagonal gradient. True screen blend is impossible inside a transparent-PNG overlay (no backdrop in the alpha stream); a light accent-white gradient alpha gives the same read over footage. Noted, not hidden. |
| 1.11 | Every hard cut gets a varied 6–10f transition | DONE (Stage A) | New `transitions.py` detects cuts, injects a rotating 8–10f fx (peak on the cut), sidecar for QC. Spin/whip need base-frame warping — deferred to Stage D theme machinery. |
| 1.12 | Text fully exits 3f before any cut; nothing across a shot change | PARTIAL — **interpretation, needs your call** | No cut awareness existed. BUT the literal rule collides with this footage: the episode cuts every 1–2 s (20 verified cuts in the 28.8 s test), shots are 1.0–1.7 s, and counters/panels/word-sync need longer than one shot — no timeline can satisfy "fully out 3f before every cut" AND "words land on their spoken frames" at once. Enforced instead (QC `cuts`): every cut transitioned; an exit may not be *in progress* at a cut unless it completes inside that cut's transition (8f exit ≤ 8–10f transition, so it's invisible); exits ending ≥3f early and established graphics riding through a transitioned cut are clean. Masked-exit count is printed in every QC report, never hidden. **If you want the literal rule, say so: Stage D's decide.py then authors per-shot (counters become kinetic words on fast-cut footage).** |
| 1.13 | Cover edge artifacts / other platforms' logos (keep only campaign-required) | PARTIAL | Crops on test bases are verified clean by eye; clipper-side QC has the corner-logo check. Automated cover tooling is an any-input concern → Stage D. Flagged, not silently dropped. |
| 1.14 | Counter counts 0.8–1.0 s ease-out, lands on spoken word, pulse 100→106→100 | DONE (Stage A) | countDur schema 0.8–1.0; landing pulse 106%; `at` = count start placed on the spoken number. |
| 1.15 | Any graphic >0.8 s keeps moving (drift 100→103%, shine ~1.2 s, glow pulse) | DONE (Stage A) | Engine: poster/card drift 100→103%, chip shine sweep 1.2 s, wraps drift, counter glow pulse, stills push-in; QC `idle` passes on all three videos. |
| 1.16 | ≤3 s dwell; panels add items ≤1.5 s apart; finished panel exits ≤1 s | DONE (Stage A) | Validator + QC enforce; decide emits +0.95 s tails. |
| 1.17 | Exits 8f: 12 px slide + blur + fade | DONE (Stage A) | `exitFade` 8f profile everywhere (words, chips, cards, counters, panels, PiP/B-roll). |
| 1.18 | Visual change ≥ every 1.5 s, never >2.5 s | DONE | QC `pacing` passes both demos (worst 2.45 s). QC now also warns >1.5 s. |
| 1.19 | Image relevance = specific concrete thing; ≤1 image per 6–8 s | PARTIAL | Cadence DONE (validator + QC ≥6 s); relevance scoring = Stage B (CLIP). |
| 1.20 | Full-bleed B-roll preferred (1.0–1.8 s, caption on top); card 55–70%, never corner | DONE (Stage A) | `fullbleed` (validated 1.0–1.8 s) / `card` (60–70%) modes; PiP schema 0.55–0.70. |
| 1.21 | Image motion 100→108% push or parallax; shadow/glow border; grain matched | PARTIAL | Push-in existed (107→115% abs on B-roll); normalised to the spec range. Grain match = Stage B. |
| 1.22 | Generated image ⇒ ILLUSTRATIVE, never real proof | DONE | Schema + validator + rendered tag (tag type raised to 3%). |
| 1.23 | Brand lock: 1 accent + black/white (or client colours) | DONE | Schema brand + validator; grade leans footage toward accent (composite). Themes generalise this in Stage D. |

## Part 2 — image quality → Stage B (all MISSING today, by stage design)

Photoreal prompt discipline (subject/camera/lighting/palette), fixed
negative prompt, 4 candidates/slot, ≥1080×1920 gate, Laplacian sharpness,
exposure + palette-distance rejects, CLIP relevance (open_clip) with
honest "unavailable" fallback + mandatory review flag, one-shot regen
then no-image fallback, grade/grain match, subject crop, per-video
style consistency, `review_pack/images/` archive. Current state: two
hand-generated stills in `motion/test_assets/`, marked illustrative.

## Part 3 — sound → Stage C

| Rule | Status |
|------|--------|
| Sound on the exact frame of every graphic event | PARTIAL — whoosh per item start + pop per chip/counter-land/plate exists (composite SFX list); no per-event QC |
| ~1 sound/s, 3–5 variants, ±10% vol, ±3% pitch | MISSING — single whoosh.wav/pop.wav, fixed gain |
| Typing sound flag `--typing-sound on/off` | DONE in the ASS pipeline (clipper), not yet wired into motion composite → Stage C |
| Sub-bass bed, risers/booms, silence dips | MISSING |
| Mix −14 LUFS / true peak <−1 dBTP | PARTIAL — current finals ≈ −15.9 LUFS / −3 dBFS, no loudnorm pass |
| CC0 licences file | PARTIAL — assets licences tracked for clipper sfx; motion inherits |

## Part 4 — any video → Stage D (all MISSING today)

Themes as config (≥5), auto-brand colour extraction, `--seed` variation
+ choice log, 16:9/9:16/1:1 + face-tracked reframing, multi-speaker,
filler/pause removal, auto-hook selection, QC-fail → simpler retry →
poster fallback, `decision_log.json`. The motion layer today is
1080×1920-only by schema (const), one hand-picked accent per timeline.

## Part 5 — review pack + QC report

| Piece | Status |
|-------|--------|
| Contact sheet 1f/0.5 s | DONE (`composite.py --sheet`) |
| 5-frame strips around transitions | DONE (strips at every item start) |
| Frames 0–10 strip | DONE (Stage A review pack) |
| `review_pack/images/` | Stage B |
| `decision_log.json` | Stage D |
| Per-word offsets / per-element sizes, contrast, margins, face, transition overlap | DONE (Stage A, QC v2, 12 checks) |
| Per-graphic enter/hold/idle/exit frames | QC v2 dwell + idle-by-construction report |
| Transition list | QC v2 from the transitions sidecar |
| Sounds/sec + offsets; LUFS + true peak | Stage C |
| "Never call a render correct until every hard rule passes" | Enforced by QC exit code; review pack ships the report verbatim |

## Stage A fix order (this stage)

PARTIALs first (1.2, 1.4–1.10, 1.14, 1.16–1.17, 1.20–1.21), then
MISSING Part-1 items (1.11, 1.12, 1.15, frames 0–10 QC). After every
change: re-render the stage-1 (10 s) and stage-2 (28.8 s) tests and the
3-source suite (MILK grading, MILK budget, Sartain podcast) and confirm
no regression before packaging the review pack.
