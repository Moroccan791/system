"""Stage C sound: frame-exact events, synthesis sanity, flag gating."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "motion"))
import sound  # noqa: E402

TL = {"items": [
    {"type": "poster", "at": 1.0, "until": 2.6,
     "rows": [[{"w": "HELLO", "at": 1.0, "kind": "key"},
               {"w": "there", "at": 1.2},
               {"w": "WORLD", "at": 1.9, "kind": "key"}]]},
    {"type": "counter", "at": 3.0, "until": 5.0, "countDur": 0.9},
    {"type": "list", "at": 6.0, "until": 8.0,
     "items": [{"text": "A", "at": 6.0}, {"text": "B", "at": 6.7}]},
]}
CUTS = [{"t": 2.5, "kind": "flare"}, {"t": 7.0, "kind": "flash"}]


def _events(typing=True):
    return sound.build_events(TL, CUTS, typing, np.random.default_rng(7))


def test_impact_lands_exactly_on_cut_frame():
    ev = _events()
    impacts = {round(e["t"], 3) for e in ev
               if e["kind"] in ("impact", "snap")}
    assert {2.5, 7.0} <= impacts
    risers = [e for e in ev if e["kind"] == "riser"]
    assert risers and abs(risers[0]["t"] - (2.5 - 0.45)) < 1e-6


def test_counter_lands_on_the_word():
    ev = _events()
    land = [e for e in ev if e["kind"] == "land"]
    assert land and abs(land[0]["t"] - 3.9) < 1e-6
    ticks = [e for e in ev if e["kind"] == "tick"]
    assert len(ticks) == 3 and all(3.0 <= t["t"] < 3.9 for t in ticks)


def test_typing_flag_gates_keystrokes():
    on = [e for e in _events(True) if e["kind"] == "key"]
    off = [e for e in _events(False) if e["kind"] == "key"]
    assert len(on) == 2 and off == []  # first word + keyword word only


def test_phrase_reveal_typing_sound_uses_group_display_time():
    tl = {"items": [{
        "type": "poster", "at": 0.0, "until": 1.5,
        "rows": [[
            {"w": "My", "at": 0.0, "showAt": 0.0},
            {"w": "worth", "at": 0.22, "showAt": 0.0, "kind": "key"},
            {"w": "isn't", "at": 0.48, "showAt": 0.0},
        ]],
    }]}
    events = sound.build_events(tl, [], True, np.random.default_rng(7))
    keys = [event for event in events if event["kind"] == "key"]
    assert len(keys) == 2
    assert [event["t"] for event in keys] == [0.0, 0.0]


def test_synthesis_is_finite_and_bounded():
    rng = np.random.default_rng(7)
    for kind in ("key", "pop", "pop_low", "tick", "land", "whoosh",
                 "riser", "impact", "snap", "swipe"):
        x = sound.synth(kind, rng)
        assert len(x) > 100 and np.all(np.isfinite(x))
        assert float(np.max(np.abs(x))) <= 1.6
