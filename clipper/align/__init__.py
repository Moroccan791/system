"""Voice activity detection and word-timing estimation.

Why this module exists: fast ASR engines that run offline on CPU (moonshine,
pocketsphinx-style models, whisper.cpp) often return text without per-word
timings. Captions need timings, so we get them in two steps:

    1. VAD (silero onnx, bundled with the `silero-vad` wheel) -> speech intervals
    2. energy alignment inside each interval -> per-word spans

Whisper with word_timestamps skips all of this; the aligner is only used when
the provider cannot give word timings.
"""
from .energy_align import align_words, assign_words_to_intervals, nuclei_times
from .vad import SileroVAD, speech_intervals

__all__ = [
    "align_words",
    "assign_words_to_intervals",
    "nuclei_times",
    "speech_intervals",
    "SileroVAD",
]
