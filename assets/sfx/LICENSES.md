# SFX license information

Every sound in this library was **synthesized in-repo with pure Python** —
no third-party recordings, no downloads of unknown provenance. All files
are original program output and are released as **CC0** (public domain
dedication): use them in any video, commercial or not, no attribution
required.

| File | How it is made | Generator |
| --- | --- | --- |
| `whoosh.wav` | swept filtered noise | synthesized in-repo (one-off generator, see git history) |
| `riser.wav` | rising chirp | synthesized in-repo (one-off generator, see git history) |
| `pop.wav` | short decayed sine | synthesized in-repo (one-off generator, see git history) |
| `tick.wav`, `tick2.wav` | filtered-noise ticks (legacy caption ticks) | synthesized in-repo (one-off generator, see git history) |
| `keys/key1.wav` … `keys/key5.wav` | five soft keystroke variants: band-passed noise tick + low sine "thock", 80 ms, 48 kHz | `clipper/captions/keysfx.py` |
| `keys/enter.wav` | two-part enter key (press + release), ~155 ms, 48 kHz | `clipper/captions/keysfx.py` |

| `../music/dark.wav`, `../music/bright.wav`, `../music/chill.wav` | synthesized chord-pad music beds (32 s loops, 48 kHz) | `clipper/captions/musicbed.py` |

Regenerate the key bank any time with:

```bash
python -m clipper.captions.keysfx
```

If a recorded sample is ever added, it must be CC0 (e.g. Freesound CC0)
and its source URL + license must be recorded in this file before use.
