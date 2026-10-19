# 01 — PRO CAPTIONS (Not AI Slop)

## Why yours look like AI slop
- Every word same size/color → no hierarchy → viewer doesn't know what matters
- White box behind text → covers footage, screams auto-generated
- Words pop on every beat → chaotic, no rhythm
- Placed dead-center over faces → unprofessional

## Pro Caption System (Used by Hormozi, Iman, Viral Podcast editors)

### 1. Hierarchy Rules (Do this for every reel)
```
Line 1 (Hook):    2-3 WORDS MAX, Biggest, YELLOW/WHITE, center top safe zone
Line 2 (Body):    Smaller, white 90%, center middle
Emphasis word:    ONE word per sentence is YELLOW (#FFD60A) + Scale 110% + slight pop
Never:            More than 6 words on screen at once
```

**Example from your Sartain raw:**
```
AI Slop:       "Women Will Only Make You Wait If You're A Beta" (all white, same size, 10 words)
Pro:           "WAIT" (huge yellow) 
               "if you're a beta" (small white underneath)
```

### 2. Position Zones (Never cover faces)
```
Safe zones for 9:16:
Top 18%    → HOOK area (big yellow hook)
Middle 45% → Keep CLEAR for faces (podcast guests)
Bottom 22% → BODY captions (white small)
Bottom 8%  → Leave for platform UI (likes/comments)
```

Your podcast tutorial `Viral-Podcast-Reels-in-Premiere-Pro-Fast-Minimal-Text-Animation` already shows this — minimal text animation, not full-sentence boxes.

### 3. Animation (Minimal, Not Bouncy)
```
AI Slop:  Pop + bounce on every word (30 frames, spring ease)
Pro:      12 frames, ease-out, 1 of 3 moves ONLY:
  - Pop-Scale: 100% → 108% → 100% in 12f (for emphasis word only)
  - Slide-Up: 20px up + fade in 10f (for body line)
  - Typewriter: 1 char per 2f (for hooks only, use once per video)
Never:    Spin, glitch, chromatic on captions
```

### 4. Presets to Install (One-Click)
We give you 3 presets — import in Premiere/CapCut/DaVinci:

| Preset | Use | Font | Color | Animation |
|---|---|---|---|---|
| **HOOK_YELLOW** | First 3 seconds | Anton 72pt | #FFD60A + white stroke 4px | Slide-Up 10f |
| **BODY_WHITE** | 90% of video | Inter Bold 42pt | #FFFFFF 90% | Pop-Scale on 1 word only |
| **PUNCH_BIG** | Final "No." / "Wait" | Bebas Neue 110pt | #FFFFFF + heavy shadow | Hold 2s, no animation |

**How to install:**
- Premiere: `Essential Graphics > Import MOGRT > 04_TEMPLATES_PRESETS/HOOK_YELLOW.mogrt` (we link download below)
- CapCut: Import `.capcut_template` from same folder
- CapCut Desktop: Drag `HOOK_YELLOW` to Favorites

### 5. Speed Trick (Fixes "too slow")
Old way: Type each caption manually → 30 min per 40s reel
Pro way: 
1. Transcribe with Whisper (auto, 30s) → gets rough words + timing
2. Run our `caption_cleaner.py` in `05_WORKFLOW` → auto-splits to 2-3 word hierarchy + picks emphasis word (noun/verb) → 80% done in 10 sec
3. You only tweak 2-3 yellow words + fix timing nudge (2 min total)

**Result:** 30 min → 3 min per reel, and looks pro because *you* chose the emphasis, not AI.

### Your fonts (Install these, delete others)
- **Display:** Anton / Bebas Neue (HOOKS only, free Google Fonts)
- **Body:** Inter Bold (captions, lower thirds)
- **Mono:** JetBrains Mono (timer / stats like "80%")

Don't use more than these 3. Ever.

### Before/After Example
```
BEFORE (AI slop):
"80% Of Men Aren't Going To Succeed" — all white, centered, covers face, pops every word

AFTER (Pro):
[Top, YELLOW, 72pt] 80% 
[Middle, white, 42pt] of men aren't going to
[Bottom, YELLOW, 110pt] SUCCEED.  (hold, scale 108%)
```

See `06_EXAMPLES_BEFORE_AFTER/` for your Butterfly re-edit mock.

