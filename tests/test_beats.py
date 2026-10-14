"""Story arcs: a clip must know where to start and where to stop."""

from clipper.asr.base import Word
from clipper.select import beats


def W(start, dur, text):
    return Word(text=text, start=start, end=start + dur)


def test_breath_groups_survive_unsorted_asr_words():
    words = [W(5.0, 0.3, "later"), W(0.0, 0.3, "first"), W(0.4, 0.3, "words")]
    groups = beats.breath_groups(words)
    assert groups[0][0].text == "first" and len(groups) == 2


def test_scan_finds_hook_payoff_silence_arc():
    words, t = [], 0.0
    for text in "Have you ever been friendzoned by a guy you liked?".split():
        words.append(W(t, 0.28, text)); t += 0.32
    for i in range(30):                       # the build: answers around the table
        words.append(W(t, 0.28, f"answer{i}")); t += 0.32
    words.append(W(t, 0.4, "percent.")); t += 3.0   # payoff, then real silence
    for text in "Next topic starts here now".split():
        words.append(W(t, 0.28, text)); t += 0.32
    arcs = beats.scan_arcs(words, min_s=5.0, max_s=60.0)
    assert arcs, "no arc found in a textbook hook->payoff->silence shape"
    a = arcs[0]
    assert a["start"] <= 0.35 and a["duration"] >= 5.0
    assert a["end"] < words[-5].start, "arc ran into the next topic"


def test_find_arc_refuses_unbounded_crosstalk():
    words, t = [], 0.0
    for i in range(200):                      # two minutes, never a breath
        words.append(W(t, 0.35, f"word{i}")); t += 0.4
    arc = beats.find_arc(words, 10.0, 11.0, min_s=20.0, max_s=60.0)
    assert arc and arc.get("unbounded"), "crosstalk must be reported, not arc-shaped"


def test_find_arc_reports_too_short_honestly():
    words = [W(0.0, 0.3, "Worst"), W(0.35, 0.4, "statistic"), W(0.8, 0.3, "ever."),
             W(4.0, 0.3, "Next"), W(4.35, 0.3, "topic")]
    arc = beats.find_arc(words, 0.0, 1.1, min_s=20.0, max_s=60.0)
    assert arc and arc["too_short"] and arc["duration"] < 20.0
