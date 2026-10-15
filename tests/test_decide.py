"""Decision rules: transcript -> draft motion timeline (motion/decide.py)."""
import importlib.util
import json
import subprocess
import sys

SPEC = importlib.util.spec_from_file_location("decide", "motion/decide.py")
decide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decide)


def words(spec):
    """spec: 'word@start word@start ...' -> transcript word dicts."""
    out = []
    for tok in spec.split():
        w, t = tok.rsplit("@", 1)
        out.append({"text": w, "start": float(t), "end": float(t) + 0.25})
    return out


def classify(spec):
    log = []
    items = []
    for u in decide.utterances(words(spec)):
        items += decide.classify(u, log)
    return decide.repair(items, 120.0), log


def types(items):
    return [i["type"] for i in items]


def test_money_headline_is_a_counter():
    items, _ = classify("You@0.1 only@0.3 have@0.5 $2,500@0.8 for@1.1 the@1.3 needs@1.5")
    assert "counter" in types(items)
    c = next(i for i in items if i["type"] == "counter")
    assert c["value"] == 2500 and c["prefix"] == "$"
    assert "NEEDS" in c["label"]


def test_bare_number_word_is_not_a_counter():
    items, _ = classify("With@0.1 milk@0.3 is@0.6 definitely@0.8 one@1.2 "
                        "of@1.4 those@1.6 big@1.9 needs@2.1 that@2.4 fits@2.6")
    assert "counter" not in types(items)


def test_comma_enumeration_is_a_list():
    items, _ = classify("The@0.1 top@0.3 three@0.5 needs@0.8 are@1.1 food,@1.4 "
                        "shelter@1.8 and@2.1 transportation,@2.3 today@3.0")
    lst = next(i for i in items if i["type"] == "list")
    assert [p["text"] for p in lst["items"]] == ["FOOD", "SHELTER", "TRANSPORTATION"]


def test_chant_is_not_a_list():
    items, _ = classify("go,@0.1 go,@0.3 go,@0.5 go,@0.7 now@1.0")
    assert "list" not in types(items)


def test_percent_allocations_are_a_process():
    items, _ = classify("Spend@0.1 50%@0.4 needs,@0.7 30%@1.2 wants,@1.5 "
                        "20%@2.0 save@2.3 today@2.6")
    proc = next(i for i in items if i["type"] == "process")
    assert [s["text"] for s in proc["steps"]] == ["NEEDS", "WANTS", "SAVE"]
    assert proc["steps"][0]["sub"] == "50%"


def test_short_strong_claim_is_a_card():
    items, _ = classify("We@0.1 cannot@0.3 get@0.6 caught@0.8")
    assert "card" in types(items)


def test_emotional_keyword_goes_neon():
    items, _ = classify("a@0.1 bunch@0.3 of@0.5 crazy@0.7 led@1.0 lights@1.2 here@1.5")
    flat = [w for i in items for r in (i.get("rows") or []) for w in r]
    crazy = next(w for w in flat if w["w"] == "CRAZY")
    assert crazy["kind"] == "neon"


def test_rule_token_is_not_a_number():
    # "50-30-20" must not glue into a 503020 counter
    items, _ = classify("about@0.1 the@0.3 50-30-20@0.5 rule@0.9 today@1.2")
    assert "counter" not in types(items)


def test_poster_stacks_never_overlap():
    items, _ = classify("one@0.10 two@0.25 three@0.40 four@0.55 five@0.70 "
                        "six@0.85 seven@1.00 eight@1.15 nine@1.30 ten@1.45 "
                        "eleven@1.60 twelve@1.75 thirteen@1.90 fourteen@2.05")
    posters = [i for i in items if i["type"] == "poster"]
    for a, b in zip(posters, posters[1:]):
        assert b["at"] >= a["until"] - 0.25


def test_generated_timelines_validate(tmp_path):
    transcript = {"words": words(
        "You@0.1 only@0.3 have@0.5 $2,500@0.8 for@1.1 the@1.3 needs@1.5 "
        "A@2.2 TV,@2.4 a@2.6 gaming@2.8 console,@3.1 and@3.4 basketball@3.6 "
        "We@5.0 cannot@5.2 get@5.5 caught@5.7")}
    src = tmp_path / "tr.json"
    out = tmp_path / "tl.json"
    src.write_text(json.dumps(transcript))
    r = subprocess.run([sys.executable, "motion/decide.py", str(src), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "motion/validate.py", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "timeline OK" in r.stdout
