"""Campaign rules: the campaign's brief as data, checked like any other stage.

The rules are not style - they cannot be learned from the references - so the
engine has to be predictable and every verdict has to carry its own reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clipper import config, guideline

RULES = {
    "campaign": "demo",
    "clip": {"min_seconds": 20, "max_seconds": 180},
    "hook": {"within_seconds": 5},
    "topics": {"approved": ["dating", "confidence"], "banned": ["politic", "money", "wealth"]},
    "entities": {"banned": ["bilzerian"]},
    "phrases": {"banned": ["you live in a country*"]},
    "tone": {"warn": ["all women are"]},
    "brand": {"face_min_coverage": 0.5, "notes": ["Michael must appear in 50% of the clip"]},
}


def candidate(**extra):
    base = {"id": "#01", "start": 0.0, "end": 30.0, "duration": 30.0,
            "text": "so i started dating again and my confidence came back", "score": 0.6}
    return {**base, **extra}


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("You live in a country where nobody...", True),
    ("you LIVE in a country", True),
    ("he said you live in a country with cheap rent", True),
    ("you live in a flat", False),
])
def test_banned_phrases_match_loosely_but_not_randomly(text, expected):
    hits = guideline.phrase_hits(text, ["you live in a country*"])
    assert bool(hits) is expected


@pytest.mark.parametrize("text,hit", [
    ("the politics of dating", "politic"),
    ("how much money does it take", "money"),
    ("generational wealth is a lie", "wealth"),
    ("POLITICAL views, honestly", "politic"),
    ("he dated her for years", None),
])
def test_banned_topics_catch_their_forms(text, hit):
    hits = guideline.keyword_hits(text, ["politic", "money", "wealth"])
    assert (hit in hits) if hit else hits == []


def test_text_verdict_rejects_bans_and_boosts_approvals():
    banned = guideline.text_verdict("nobody tells you how much money dating costs", RULES)
    assert banned["reject"] is True
    assert any("money" in reason for reason in banned["banned"])
    assert any("off-campaign" in reason for reason in banned["reasons"])

    good = guideline.text_verdict("my confidence on dates changed everything", RULES)
    assert good["reject"] is False
    assert good["boost"], "an approved topic should be reported"
    assert any("on-campaign" in reason for reason in good["reasons"])


def test_banned_names_and_tone_warnings():
    assert guideline.text_verdict("I was with Dan Bilzerian that night", RULES)["reject"]
    tone = guideline.text_verdict("all women are like that", RULES)
    assert tone["warn"] and not tone["reject"], "a framing warning is not an automatic rejection"


# ---------------------------------------------------------------------------
# length, hook, compliance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seconds,ok", [(19.0, False), (20.0, True), (30.0, True),
                                        (180.0, True), (181.0, False)])
def test_length_verdict_follows_the_campaign_window(seconds, ok):
    passed, why = guideline.length_verdict(seconds, RULES)
    assert passed is ok
    assert "window" in why or "maximum" in why or "minimum" in why


def test_hook_verdict_checks_the_first_seconds():
    ok, why = guideline.hook_verdict("why do people ignore the best offer?", 1.2, RULES)
    assert ok and "1.2s" in why
    late, why = guideline.hook_verdict("and then we talked about the weather", 12.0, RULES)
    assert not late and "12.0s" in why


def test_compliance_reports_every_check_with_its_reason():
    result = guideline.compliance(candidate(), RULES, hook_at=1.0)
    checks = {c["check"]: c for c in result["checks"]}
    assert set(checks) >= {"length", "topics", "hook", "format"}
    assert result["pass"] is True
    assert all(c["detail"] for c in result["checks"]), "every check explains itself"
    assert any("face" in note for note in result["notes"]), "unmeasured brand rules stay visible"


def test_compliance_fails_on_a_banned_topic_and_a_bad_length():
    result = guideline.compliance(candidate(text="how much money do you make", duration=5.0), RULES)
    assert result["pass"] is False
    failed = {c["check"] for c in result["checks"] if not c["pass"]}
    assert {"length", "topics"} <= failed


# ---------------------------------------------------------------------------
# loading and scaffolding
# ---------------------------------------------------------------------------
def test_campaign_rules_load_from_the_campaign_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAMPAIGNS", tmp_path / "campaigns")
    (tmp_path / "campaigns" / "mycamp").mkdir(parents=True)
    guideline.save({**RULES, "campaign": "mycamp", "clip": {"min_seconds": 30, "max_seconds": 90}},
                   tmp_path / "campaigns" / "mycamp" / "campaign.json")
    loaded = guideline.load("mycamp")
    assert loaded["path"].endswith("campaign.json")
    assert guideline.clip_length(loaded) == (30.0, 90.0)
    assert loaded["hook"]["within_seconds"] == 5, "missing fields come from the defaults"


def test_campaign_without_rules_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CAMPAIGNS", tmp_path / "campaigns")
    loaded = guideline.load("nothing_here")
    assert loaded["path"] is None
    assert guideline.clip_length(loaded) == (15.0, 60.0)


def test_scaffold_writes_something_loadable(tmp_path):
    path = guideline.scaffold("mycamp", tmp_path / "campaign.json")
    assert path.exists()
    loaded = guideline.load(None, path)
    assert loaded["campaign"] == "mycamp"
    assert guideline.clip_length(loaded) == (20.0, 180.0)
