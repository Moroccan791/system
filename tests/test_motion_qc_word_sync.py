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


def test_phrase_reveal_reports_anticipation_without_weakening_word_sync():
    transcript = {"words": [
        {"text": "I", "start": 0.0, "end": 0.1},
        {"text": "am", "start": 0.4, "end": 0.6},
        {"text": "fine", "start": 0.8, "end": 1.0},
    ]}
    timeline = {"items": [{
        "type": "poster", "at": 0.067, "until": 1.2,
        "rows": [[
            {"w": "I", "at": 0.067, "showAt": 0.067},
            {"w": "am", "at": 0.467, "showAt": 0.067},
            {"w": "fine", "at": 0.867, "showAt": 0.067},
        ]],
    }]}

    status, detail = word_sync(timeline, transcript)

    assert status == "pass", detail
    assert "3 phrase-revealed together" in detail
    assert "up to 0.7s early" in detail


def test_phrase_reveal_qc_rejects_excessive_lookahead():
    transcript = {"words": [
        {"text": "I", "start": 0.0, "end": 0.1},
        {"text": "waited", "start": 2.0, "end": 2.2},
    ]}
    timeline = {"items": [{
        "type": "poster", "at": 0.067, "until": 2.4,
        "rows": [[
            {"w": "I", "at": 0.067, "showAt": 0.067},
            {"w": "waited", "at": 2.067, "showAt": 0.067},
        ]],
    }]}

    status, detail = word_sync(timeline, transcript)

    assert status == "fail"
    assert "phrase-reveal cap" in detail
