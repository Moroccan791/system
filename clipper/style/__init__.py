"""Stage 1 - learn a campaign's style from the creator's reference clips.

Four analysers run over every reference video:

    shots.py             where the cuts are          -> pacing
    zoom.py              punch-ins / slow pushes     -> zoom
    captions_detect.py   caption look (colour, size, position, karaoke, casing)
    audio_style.py       loudness, speech, music bed -> audio

`extract.py` aggregates them into styles/<campaign>.style.json and keeps
evidence (annotated frames + a report) in work/<campaign>/style/ so every
number can be checked by eye instead of trusted.
"""
from .extract import extract_style

__all__ = ["extract_style"]
