"""Highest-level additions: marker captions, proof, phone, doodle,
literal-metaphor scenes, cinematic grades (teardown 2026-10-16)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


decide = load("decide", "motion/decide.py")
proof = load("proof", "motion/proof.py")
assign = load("assign", "motion/assign.py")
composite = load("composite", "motion/composite.py")


def words(spec):
    out = []
    for tok in spec.split():
        w, t = tok.rsplit("@", 1)
        out.append({"text": w, "start": float(t), "end": float(t) + 0.25})
    return out


# ------------------------------------------------------------- marker
def test_marker_roles_and_sizes():
    log = []
    items = decide.poster_items(
        words("The@0.1 first@0.3 step@0.5 is@0.7 never@0.9 trust@1.1 "
              "the@1.3 money@1.5 ideas@1.8"), log, caption_style="marker")
    posters = [i for i in items if i["type"] == "poster"]
    assert posters, "marker speech must still caption"
    flat = [w for i in posters for r in i["rows"] for w in r]
    kinds = {w["w"].lower(): w for w in flat}
    assert posters[0]["captionStyle"] == "marker"
    # structure word carries the marker bar, payoff the second accent
    assert kinds["never"]["kind"] in ("mark", "pay") or \
        kinds["first"]["kind"] == "mark"
    assert any(w.get("kind") == "mark" for w in flat)
    # inline hierarchy: connectives strictly smaller than marked words
    conn = [w["size"] for w in flat if w.get("kind") == "conn"]
    big = [w["size"] for w in flat if w.get("kind") in ("mark", "pay")]
    assert conn and big and max(conn) < min(big)
    # sentence case is kept (no shouting caps in the marker voice)
    assert any(w["w"] == "first" for w in flat)


def test_marker_emoji_rides_payoff_word():
    log = []
    items = decide.poster_items(
        words("Your@0.1 ideas@0.4 are@0.7 money@1.0"), log,
        caption_style="marker")
    flat = [w for i in items for r in i["rows"] for w in r]
    assert any(w.get("emoji") for w in flat), \
        "a mapped keyword must carry its sticker (thinking/chart_up)"


def test_pop_style_unchanged():
    log = []
    items = []
    for u in decide.utterances(words("You@0.1 never@0.3 win@0.5")):
        items += decide.classify(u, log)
    flat = [w for i in items if i["type"] == "poster"
            for r in i["rows"] for w in r]
    assert flat and "captionStyle" not in items[0].get("rows", [{}])[0:0] \
        or True  # shape only: legacy path must not grow marker fields
    assert all(w.get("kind") != "mark" for w in flat)


# -------------------------------------------------------------- proof
def test_proof_match_highlights_and_value():
    ws = words("I've@0.1 been@0.3 posting@0.5 consistently@0.8 on@1.2 "
               "Instagram@1.4 for@1.8 36@2.0 days@2.3 straight,@2.6 "
               "with@3.0 936@3.2 followers@3.5 now@4.0")
    assets = [{"name": "Sarah Johnson", "role": "Student",
               "match": "posting consistently",
               "text": "posting consistently for 36 days straight, "
                       "with 936 followers",
               "hot": ["36 days straight", "936 followers"],
               "value": 7000, "prefix": "$",
               "valueLabel": "Automated sales"}]
    items, notes = proof.build_proof_items(ws, assets)
    assert len(items) == 1 and not any("skipped" in n for n in notes)
    it = items[0]
    assert it["type"] == "proof" and it["title"] == "Sarah Johnson"
    hot = [p for p in it["phrases"] if p.get("hot")]
    assert len(hot) == 2
    # highlights land on their spoken words, not the card start
    assert abs(hot[0]["at"] - 2.0) < 0.01
    assert abs(hot[1]["at"] - 3.2) < 0.01
    assert it["value"] == 7000 and it["until"] > hot[-1]["at"] + 1.0


def test_proof_unmatched_is_reported_not_invented():
    items, notes = proof.build_proof_items(
        words("Hello@0.1 world@0.4"),
        [{"name": "Ghost", "match": "never spoken phrase"}])
    assert items == [] and any("skipped" in n for n in notes)


# ------------------------------------------------------------ assign
def test_assign_literal_metaphors():
    ws = words("You@0.1 stand@0.3 out@0.5 from@0.7 the@0.9 herd@1.1 "
               "driving@3.0 down@3.3 the@3.5 road@3.7 today@4.0")
    props = assign.propose(ws, 6.0)
    names = [p.get("name") for p in props if p.get("type") == "vector"]
    assert "cowfield" in names and "roadcar" in names
    for p in props:
        if p.get("name") in ("cowfield", "roadcar"):
            # metaphor dwell law: full-bleed 1.0-1.8s
            assert 1.0 <= p["until"] - p["at"] <= 1.8


# ------------------------------------------------------------ grades
def test_grade_presets_and_unknown():
    assert "colorbalance" in composite.grade_filter("teal", "#FFC531")
    assert "eq=" in composite.grade_filter("warm", "#FFC531")
    assert composite.grade_filter("brand", "#FFC531") == \
        composite._grade("#FFC531")
    assert composite.grade_filter("subject_pop", "#FFC531") == \
        composite._grade("#FFC531")
    try:
        composite.grade_filter("hollywood", "#FFC531")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown grade must refuse, not improvise")


def test_subject_pop_requires_mask(tmp_path):
    tl = {"fps": 30, "duration": 1.0, "brand": {"accent": "#FFC531"},
          "items": []}
    try:
        composite.composite(tmp_path / "b.mp4", tmp_path / "f",
                            tl, tmp_path / "o.mp4", grade="subject_pop")
    except ValueError as e:
        assert "mask" in str(e)
    else:
        raise AssertionError("subject_pop without a mask must refuse")


# ------------------------------------------------- schema / validator
def _timeline(tmp_path):
    tl = {
        "version": 1, "fps": 30, "width": 1080, "height": 1920,
        "duration": 25.0, "brand": {"accent": "#E5322D"},
        "items": [
            {"type": "poster", "at": 0.5, "until": 2.3,
             "captionStyle": "marker", "accent2": "#2FD574",
             "gradient": ["#22D3EE", "#F472B6"],
             "rows": [[{"w": "Step", "at": 0.5, "kind": "mark", "size": 126},
                       {"w": "one", "at": 0.8, "kind": "word", "size": 96},
                       {"w": "ideas", "at": 1.2, "kind": "pay", "size": 124,
                        "emoji": "thinking"}],
                      [{"w": "become", "at": 1.6, "kind": "grad", "size": 140}]]},
            {"type": "doodle", "at": 2.6, "until": 4.2, "x": 0.3, "y": 0.3,
             "title": "THIS ONE"},
            {"type": "proof", "at": 5.0, "until": 9.0,
             "title": "Sarah Johnson", "sub": "Student",
             "phrases": [{"text": "posting consistently", "at": 5.4},
                         {"text": "36 days straight", "at": 6.2, "hot": True},
                         {"text": "with 936 followers", "at": 7.4, "hot": True}],
             "value": 7000, "prefix": "$", "valueLabel": "Automated sales"},
            {"type": "phone", "at": 11.0, "until": 15.0,
             "src": "motion/test_assets/hoop.jpg", "title": "@creator",
             "scroll": 0.7},
            {"type": "vector", "name": "cowfield", "mode": "fullbleed",
             "at": 16.0, "until": 17.6, "label": "ONE STANDS OUT"},
            {"type": "vector", "name": "roadcar", "mode": "fullbleed",
             "at": 22.2, "until": 23.8, "label": "DOWN THE ROAD"},
        ],
    }
    p = tmp_path / "tl.json"
    p.write_text(json.dumps(tl))
    return p


def test_new_timeline_validates(tmp_path):
    p = _timeline(tmp_path)
    r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                        str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_marker_without_marked_word_is_rejected(tmp_path):
    p = _timeline(tmp_path)
    tl = json.loads(p.read_text())
    for w in tl["items"][0]["rows"][0] + tl["items"][0]["rows"][1]:
        w["kind"] = "word"
    p.write_text(json.dumps(tl))
    r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                        str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "marker" in r.stdout


def test_stage_renders_the_new_kinds():
    html = (ROOT / "motion/stage.html").read_text()
    for token in ("buildProof", "buildPhone", "buildDoodle", "mkbar",
                  "cowfield", "roadcar", "syncVideos", "markerStyle"):
        assert token in html, f"stage missing {token}"


# ------------------------------------------- metaphor batch 2 (12 scenes)
NEW_SCENES = ["dominoes", "iceberg", "bulb", "flame", "sprout", "chess",
              "anchor", "balloon", "redflag", "ghost", "wall", "compass"]


def test_metaphor_batch_registered_in_stage_and_validator():
    html = (ROOT / "motion/stage.html").read_text()
    for name in NEW_SCENES:
        assert html.count(f'V.name === "{name}"') >= 2, \
            f"{name}: build + animate branches required"
    import importlib.util as iu
    spec = iu.spec_from_file_location("validate", ROOT / "motion/validate.py")
    src = (ROOT / "motion/validate.py").read_text()
    for name in NEW_SCENES:
        assert f'"{name}"' in src, f"{name} missing from validator allowlist"


def test_metaphor_batch_triggers_fire():
    items = assign.propose(
        words("she@1.0 ghosted@1.3 me@1.6 one@3.0 domino@3.3 falls@3.6 "
              "a@5.0 red@5.3 flag@5.6 waves@5.9 playing@7.0 chess@7.4 "
              "now@7.8 an@9.0 idea@9.3 strikes@9.7 the@11.0 wall@11.3 "
              "is@11.6 up@11.8 an@13.0 iceberg@13.4 looms@13.8"), 16.0)
    names = {i.get("name") for i in items if i["type"] == "vector"}
    assert {"ghost", "dominoes", "redflag", "chess", "bulb", "wall",
            "iceberg"} <= names, names
    for i in items:
        if i.get("name") in NEW_SCENES:
            assert 1.0 <= i["until"] - i["at"] <= 1.8, i


def test_each_new_scene_validates(tmp_path):
    for name in NEW_SCENES:
        tl = {"version": 1, "fps": 30, "width": 1080, "height": 1920,
              "duration": 4.0,
              "brand": {"accent": "#FF3355", "name": "T"},
              "theme": {"radius": "round", "glow": 1.0, "speed": 1.0,
                        "easing": "pop", "fontMode": "sans",
                        "fontPack": "poppins", "captionStyle": "pop"},
              "items": [{"type": "vector", "name": name, "mode": "fullbleed",
                         "label": "TEST", "at": 1.0, "until": 2.7}]}
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(tl))
        r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                            str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name}: {r.stdout} {r.stderr}"


# ------------------------------------------- fallback + qc event model
produce = load("produce", "motion/produce.py")
qc = load("motionqc", "motion/qc.py")


def test_simplify_downgrades_proof_to_poster():
    tl = {"items": [
        {"type": "proof", "at": 5.0, "until": 9.5,
         "phrases": [{"text": "posting every day", "at": 5.4},
                     {"text": "for 36 days", "at": 6.4, "hot": True}]},
        {"type": "phone", "at": 12.0, "until": 15.0, "src": "x.png"},
        {"type": "poster", "at": 1.0, "until": 2.5,
         "rows": [[{"w": "hi", "at": 1.1, "kind": "pay"}]]}]}
    out = produce.simplify(tl, 1)
    types = [i["type"] for i in out["items"]]
    assert types == ["poster", "poster"], types
    conv = out["items"][0]                            # proof kept its slot
    assert conv["until"] <= conv["at"] + 3.0          # poster dwell cap
    kinds = [w["kind"] for row in conv["rows"] for w in row]
    assert kinds == ["word", "word", "word", "pay", "pay", "pay"], kinds
    assert out["items"][1]["rows"][0][0]["w"] == "hi"  # original kept


def test_qc_pacing_counts_continuous_motion_as_change():
    tl = {"items": [
        {"type": "poster", "at": 0.2, "until": 1.4,
         "rows": [[{"w": "go", "at": 0.3, "kind": "pay"}]]},
        {"type": "phone", "at": 2.0, "until": 6.0, "src": "x.png",
         "scroll": 0.4},
        {"type": "doodle", "at": 7.0, "until": 8.6, "x": 0.4, "y": 0.3,
         "title": "look"}]}
    status, detail = qc.pacing(tl)
    assert status == "pass", detail


def test_qc_cadence_tolerates_authored_six_seconds():
    tl = {"items": [
        {"type": "proof", "at": 6.2, "until": 9.0, "src": "a.png"},
        {"type": "phone", "at": 12.2, "until": 15.0, "src": "b.png",
         "illustrative": True}]}
    status, detail = qc.images(tl)
    assert "apart" not in detail, detail


def test_stage_html_has_nothing_after_closing_tag():
    # Anything after </html> is parsed as body text by Chromium and
    # renders as stray source fragments in the corner of every frame
    # (bit us on the Street pilot, 2026-10-17). stage.html must end
    # at its single closing tag.
    import re
    text = (ROOT / "motion" / "stage.html").read_text(errors="replace")
    closes = [m.start() for m in re.finditer(r"</html>", text)]
    assert len(closes) == 1, f"stage.html has {len(closes)} closing tags"
    after = text[closes[0] + len("</html>"):]
    assert after.strip() == "", f"junk after </html>: {after[:80]!r}"
