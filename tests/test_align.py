"""The aligner is what turns "text without timings" into karaoke timings.
Ground truth here is speech we construct ourselves, so the expected answers are
known exactly rather than eyeballed.
"""
from __future__ import annotations

import numpy as np
import pytest

from clipper.align.energy_align import align_words, assign_words_to_intervals, nuclei_times
from clipper.align.vad import energy_probs, probs_to_intervals, speech_intervals

RATE = 16000


def bursts(words: list[str], *, word: float = 0.35, gap: float = 0.30, f0: float = 160.0) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Build audio where each "word" is a tone burst separated by silence.

    Returns (audio, ground_truth_spans) - the truth is exact by construction.
    """
    chunks: list[np.ndarray] = []
    spans: list[tuple[float, float]] = []
    t = 0.0
    for i, _ in enumerate(words):
        n = int(word * RATE)
        tt = np.arange(n) / RATE
        # two formant-ish partials + amplitude envelope = speechy enough for VAD
        sig = (np.sin(2 * np.pi * f0 * tt) * 0.5 + np.sin(2 * np.pi * 2.2 * f0 * tt) * 0.2)
        env = np.minimum(1.0, np.minimum(tt / 0.04, (word - tt) / 0.04)).clip(0, 1)
        chunks.append((sig * env * 0.6).astype(np.float32))
        spans.append((t, t + word))
        silence = np.zeros(int(gap * RATE), dtype=np.float32)
        chunks.append(silence)
        t += word + gap
    return np.concatenate(chunks), spans


def test_assign_words_to_intervals_respects_order():
    words = ["one", "two", "three", "four", "five", "six"]
    groups = assign_words_to_intervals(words, [(0, 1), (1, 2), (2, 3)])
    flat = [w for g in groups for w in g]
    assert flat == words
    assert all(g for g in groups)


def test_vad_finds_each_burst():
    audio, spans = bursts(["a", "b", "c"])
    intervals = speech_intervals(audio, RATE, engine="energy", min_speech=0.15, min_silence=0.12)
    assert len(intervals) == len(spans)
    for (s, e), (ts, te) in zip(intervals, spans):
        assert abs(s - ts) < 0.10 and abs(e - te) < 0.10


def test_probs_to_intervals_merges_short_gaps():
    probs = np.array([0, 1, 1, 0, 1, 1, 1, 0], dtype=np.float32)
    spans = probs_to_intervals(probs, 0.1, min_silence=0.15, pad=0.0)
    assert spans == [(0.1, 0.7)]


def test_nuclei_detected_in_bursts():
    audio, _ = bursts(["a", "b", "c"])
    nuc = nuclei_times(audio, RATE)
    assert len(nuc) >= 3


def test_align_words_matches_ground_truth_within_200ms():
    words = ["alpha", "bravo", "charlie"]
    audio, spans = bursts(words)
    got = align_words(" ".join(words), audio, RATE, intervals=None,
                      engine="energy", min_speech=0.15, min_silence=0.12)
    assert [w.text for w in got] == words
    for w, (ts, te) in zip(got, spans):
        assert abs(w.start - ts) < 0.20, f"{w.text}: {w.start} vs {ts}"
        assert abs(w.end - te) < 0.20, f"{w.text}: {w.end} vs {te}"


def test_align_words_within_a_single_continuous_interval():
    # one long burst, four words: proportional split must cover the whole span
    audio, spans = bursts(["a", "b", "c", "d"], word=0.4, gap=0.02)
    got = align_words("one two three four", audio, RATE, intervals=[(spans[0][0], spans[-1][1])])
    assert len(got) == 4
    assert got[0].start == pytest.approx(spans[0][0], abs=0.05)
    assert got[-1].end == pytest.approx(spans[-1][1], abs=0.05)
    starts = [w.start for w in got]
    assert starts == sorted(starts)


def test_align_words_empty_text():
    audio, _ = bursts(["a"])
    assert align_words("", audio, RATE) == []


def test_energy_probs_shape():
    audio, _ = bursts(["a", "b"])
    probs, win = energy_probs(audio, RATE)
    assert probs.ndim == 1 and 0.0 <= float(probs.min()) and float(probs.max()) <= 1.0


def _burst_audio(seconds=6.0, rate=16000, bursts=(0.5, 1.5, 2.5, 3.5, 4.5, 5.5)):
    import numpy as np
    x = np.zeros(int(seconds * rate), dtype=np.float32)
    rng = np.random.default_rng(3)
    for b in bursts:
        i = int(b * rate)
        seg = rng.standard_normal(int(0.18 * rate)).astype(np.float32) * 0.5
        # speech-ish band energy: modulate a 300-3000Hz-ish burst via noise is fine
        x[i:i + len(seg)] += seg
    return x, rate


def test_nuclei_times_finds_syllable_bursts():
    """Regression: the peak picker used to reject every peak before the
    loudest one and returned ~2 nuclei for 40s of speech."""
    import numpy as np
    from clipper.align.energy_align import nuclei_times
    x, rate = _burst_audio()
    nuc = nuclei_times(x, rate)
    assert len(nuc) >= 5, f"expected a nucleus per burst, got {len(nuc)}"


def test_align_words_clamps_intervals_to_the_audio():
    """Regression: handing align_words a full-timeline interval for a short
    chunk smeared one sentence across the whole file (captions seconds away
    from the voice). Words must stay inside the audio they were given."""
    import numpy as np
    from clipper.align.energy_align import align_words
    x, rate = _burst_audio(seconds=6.0)
    words = align_words("one two three four five six", x, rate,
                        intervals=[(0.0, 40.0)])   # the old provider bug, verbatim
    assert words, "no words aligned"
    assert max(w.end for w in words) <= 6.05, "a word escaped the chunk"
    assert [w.text for w in words] == "one two three four five six".split()
