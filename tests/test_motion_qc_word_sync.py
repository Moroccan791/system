"""Regression tests for motion QC's authored-word timing alignment."""

from motion.qc import word_sync


def test_word_sync_accepts_into_split_as_in_to_after_an_earlier_into():
    transcript = {
        "words": [
            {"text": "I", "start": 0.00, "end": 0.10},
            {"text": "went", "start": 0.10, "end": 0.20},
            {"text": "into", "start": 0.20, "end": 0.40},
            {"text": "treatment", "start": 0.40, "end": 0.80},
            {"text": "she", "start": 1.00, "end": 1.10},
            {"text": "went", "start": 1.10, "end": 1.20},
            {"text": "in", "start": 1.20, "end": 1.35},
            {"text": "to", "start": 1.35, "end": 1.50},
            {"text": "treatment", "start": 1.50, "end": 1.80},
        ]
    }
    # The render engine reveals each word two frames before its acoustic
    # onset. The later caption is authored as the correct single word
    # "into", though the ASR split its audio timing into "in" + "to".
    words = [
        ("I", 0.067), ("went", 0.167), ("into", 0.267),
        ("treatment", 0.467), ("she", 1.067), ("went", 1.167),
        ("into", 1.267), ("treatment", 1.567),
    ]
    timeline = {"items": [{
        "type": "poster",
        "rows": [[{"w": text, "at": at} for text, at in words]],
    }]}

    status, detail = word_sync(timeline, transcript)

    assert status == "pass", detail
    assert "8 words" in detail
