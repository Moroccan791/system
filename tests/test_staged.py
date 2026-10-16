"""Stage D: themes, prep (hook/pauses), produce fallback helpers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "motion"))
import prep  # noqa: E402
import produce  # noqa: E402
import brand  # noqa: E402

WORDS = [
    {"text": "So", "start": 0.0, "end": 0.2},
    {"text": "um", "start": 0.2, "end": 0.4},
    {"text": "welcome", "start": 0.4, "end": 0.9},
    {"text": "back.", "start": 0.9, "end": 1.3},
    {"text": "We", "start": 2.6, "end": 2.8},
    {"text": "have", "start": 2.8, "end": 3.0},
    {"text": "$2,500", "start": 3.0, "end": 3.6},
    {"text": "today.", "start": 3.6, "end": 4.1},
    {"text": "Then", "start": 4.1, "end": 4.5},
    {"text": "we", "start": 4.5, "end": 4.7},
    {"text": "buy", "start": 4.7, "end": 5.0},
    {"text": "lights.", "start": 5.0, "end": 5.6},
    {"text": "And", "start": 5.6, "end": 5.9},
    {"text": "a", "start": 5.9, "end": 6.0},
    {"text": "hoop.", "start": 6.0, "end": 6.6},
]


def test_hook_prefers_the_number_sentence():
    h = prep.pick_hook(WORDS, window=20)
    assert h["start"] == 2.6 and "$2,500" in h["opener"]


def test_tighten_compresses_dead_air_and_remaps():
    tight, removed = prep.tighten(WORDS)
    assert removed and removed[0]["dur"] > 0.9
    we = next(w for w in tight if w["text"] == "We")
    assert we["start"] < 2.6  # shifted earlier by the removed pause
    starts = [w["start"] for w in tight]
    assert starts == sorted(starts)


def test_themes_are_five_and_complete():
    themes = sorted((Path(brand.THEMES)).glob("*.json"))
    assert len(themes) == 9
    for p in themes:
        t = json.loads(p.read_text())
        for k in ("accent", "radius", "glow", "speed", "easing",
                  "fontMode", "transitionOrder"):
            assert k in t, (p.name, k)


def test_brand_pick_maps_red_footage_to_bold_red():
    palette = [{"rgb": [200, 30, 30], "hue": 0, "sat": 0.85,
                "val": 0.8, "share": 0.3},
               {"rgb": [120, 120, 120], "hue": 0, "sat": 0.0,
                "val": 0.5, "share": 0.7}]
    pick = brand.pick_theme(palette)
    assert pick["theme"] == "bold-red" and pick["accent_override"]


def test_simplify_drops_inserts_keeps_argument():
    tl = {"items": [{"type": "poster"}, {"type": "vector"},
                    {"type": "counter"}, {"type": "fx", "kind": "flare"},
                    {"type": "fx", "kind": "opening"}]}
    out = produce.simplify(tl, 1)
    assert [i["type"] for i in out["items"]] == ["poster", "counter", "fx"]


def test_plain_captions_chunks_words():
    words = [{"text": f"w{i}", "start": i * 0.3, "end": i * 0.3 + 0.25}
             for i in range(7)]
    tl = produce.plain_captions(words, 3.0)
    assert tl["items"] and all(i["type"] == "poster" for i in tl["items"])
    assert tl["items"][0]["rows"][0][0]["w"] == "w0"
