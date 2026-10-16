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

## Part 2 — image quality → Stage B — DONE (Stage B, pack `review_b/`)

`motion/images.py` implements the full spec: prompts = sentence subject
+ rotating framing (never the same look twice in a row) + the base
video's measured lighting/palette + fixed photoreal style suffix and
negative prompt; 4 candidates/slot gated on resolution (upscale
flagged), Laplacian sharpness ≥45, clipping ≤12%, palette ΔE ≤38;
best-passing selection, grade/grain match (Reinhard Lab → video +
matched grain σ), subject crop to slot size; candidates + scores +
chosen archived to `review_b/images/`. Proven on the stage-2 video:
both slots re-sourced (hoop PiP, LED B-roll), re-render QC v2 PASS
12/12. **CLIP relevance: UNAVAILABLE, declared** — weight hosts are
egress-blocked in this sandbox, so `scores.json` carries
`clip_relevance: null` and every generated image is flagged
`needs_user_review` for the user's relevance call, per spec. Sartain
has no image slot; stage-1/Sartain Stage-A renders unchanged.

## Part 3 — sound → Stage C — DONE (Stage C, pack `review_c/`)

`motion/sound.py`: frame-exact events from the timeline (entries,
panel rows, first+keyword word keystrokes behind `--typing-sound`,
counter tick-roll landing on the word, riser-to-impact ON every cut
frame from the transitions sidecar, 130 ms bed dips before big
impacts), seeded variants with pitch/volume jitter, sub-bass bed
~24 dB under voice, generated pad ducked 12 dB under speech, voice
levelling + soft-ceiling loudness staging in the mix. All sounds
synthesised in code — CC0, `SOUND_LICENSE.md`. All 3 finals SOUND QC
PASS: impacts verified on cut frames, -14.1 LUFS, TP -1.5..-3.0 dBTP.
Density disclosed per video (1.70 accents/s on the 1.44 s-cut budget
video; ~1/s at typical cut density). Also in Stage C (user-reported):
`motion/reframe.py` face-tracked bases replace the fixed crop —
speaker face cut in 28% of frames before, 0 cut frames after
(worst margin 8 px); process panels gained dark plates.

## Part 4 — any video → Stage D — DONE (pack `review_d/`)

Themes as config (5 files in `motion/themes/`: palette, fonts, radius,
glow, speed, easing, transition order, sound pack), auto-brand colour
extraction (`brand.py`: closest theme + accent override; brand-locked
timeline accent always wins), `--seed` variation + full choice log in
`decision_log.json` (three demos = three themes/seeds), 16:9/9:16/1:1
via canvas config + face-tracked reframing (Stage C), multi-speaker at
authoring level (any speaker can be captioned/graphic subject),
filler/pause removal + auto-hook (`prep.py`, hook = number-first
scoring; 0.58 s pause found in stage-2), QC-fail → simplified →
poster-captions fallback (`produce.py`, levels recorded, never broken
output). The governing demo is `stage2_test` — vector-first (below).

**Vector-first amendment (user, Stage D):** picturable nouns are
animated SVG scenes (`vector`: hoop/led/donut/arrow/burst, deterministic
frame-clock animation, accent-true, no ILLUSTRATIVE tag), generated
photos remain fallback-with-review-flag only. Native SVG in `stage.html`
chosen over a second renderer (Motion Canvas/Lottie): same look, zero
dependencies, egress-safe. Design rule learned: author scenes in unit
width × canvas-derived height — portrait canvases are not scaled
landscape scenes (see `buildScene`).

## Part 5 — review pack + QC report — DONE

| Piece | Status |
|-------|--------|
| Contact sheet 1f/0.5 s | DONE (`composite.py --sheet`) |
| 5-frame strips around transitions | DONE (every transition, `report.py`) |
| Frames 0–10 strip | DONE (`report.py`, every render) |
| `review_pack/images/` | DONE (Stage B archive; Stage D pack carries the photo choices the vectors replaced, `review_d/images/`) |
| `decision_log.json` | DONE (Stage D, every `produce.py` render) |
| Per-word offsets / per-element sizes, contrast, margins, face, transition overlap | DONE (QC v2 + `report.py` Part-5 JSON/txt) |
| Per-graphic enter/hold/idle/exit frames | DONE (`report.py` from measured item bounds) |
| Transition list | DONE (QC v2 + `report.py`) |
| Sounds/sec + offsets; LUFS + true peak | DONE (Stage C, `sound_log.json` beside every render) |
| "Never call a render correct until every hard rule passes" | Enforced by QC exit code; `produce.py` refuses to ship below the gate without engaging the fallback chain and recording it |

## Stage A fix order (this stage)

PARTIALs first (1.2, 1.4–1.10, 1.14, 1.16–1.17, 1.20–1.21), then
MISSING Part-1 items (1.11, 1.12, 1.15, frames 0–10 QC). After every
change: re-render the stage-1 (10 s) and stage-2 (28.8 s) tests and the
3-source suite (MILK grading, MILK budget, Sartain podcast) and confirm
no regression before packaging the review pack.
