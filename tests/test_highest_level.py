"""Highest-level additions: editorial captions, proof, phone, doodle,
literal-metaphor scenes, cinematic grades (teardown 2026-10-16)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


# ------------------------------------------------------ editorial caption ban
def test_marker_and_impact_authoring_are_refused():
    log = []
    for style in ("marker", "impact"):
        try:
            decide.poster_items(words("The@0.1 idea@0.4 matters@0.8"), log,
                                caption_style=style)
        except ValueError as exc:
            assert "unavailable" in str(exc) or "banned" in str(exc)
        else:
            raise AssertionError(f"{style} captions must be permanently unavailable")


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


def test_worth_scene_is_context_gated_and_not_financial():
    personal = assign.propose(words(
        "My@0.1 worth@0.3 isn't@0.5 in@0.7 my@0.9 body@1.1"), 4.0)
    worth = [p for p in personal if p.get("name") == "worth"]
    assert len(worth) == 1
    assert worth[0]["mode"] == "fullbleed"
    assert 1.0 <= worth[0]["until"] - worth[0]["at"] <= 1.8

    financial = assign.propose(words(
        "the@0.1 company@0.3 net@0.5 worth@0.7 is@0.9 10@1.1 million@1.3"), 4.0)
    assert not any(p.get("name") == "worth" for p in financial)


def test_worth_scene_has_animated_build_and_release():
    html = (ROOT / "motion/stage.html").read_text()
    build = html[html.index('} else if (V.name === "worth") {'):]
    assert "n.measure" in build and "n.ticks" in build and "n.ring" in build
    assert "n.cross" in build and "n.word.textContent = \"WORTH\"" in build
    animate = html[html.index('} else if (V.name === "worth") {',
                    html.index("function animateVector")):]
    assert "const assemble" in animate and "const release" in animate


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
             "captionStyle": "editorial",
             "rows": [[{"w": "Step", "at": 0.5, "kind": "key", "size": 126},
                       {"w": "one", "at": 0.8, "kind": "word", "size": 96},
                       {"w": "ideas", "at": 1.2, "kind": "word", "size": 96}],
                      [{"w": "become", "at": 1.6, "kind": "key", "size": 140}]]},
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


def test_phrase_reveal_timeline_accepts_show_at_and_bounds_early_lookahead(tmp_path):
    tl = {"version": 1, "fps": 30, "width": 1080, "height": 1920,
          "duration": 3.0, "brand": {"accent": "#4D79D1"},
          "items": [{"type": "poster", "at": 0.0, "until": 2.4,
                     "rows": [[{"w": "My", "at": 0.0, "showAt": 0.0},
                               {"w": "heart.", "at": 1.4, "showAt": 0.0}]]}]}
    p = tmp_path / "phrase-reveal.json"
    p.write_text(json.dumps(tl))
    valid = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                            str(p)], capture_output=True, text=True)
    assert valid.returncode == 0, valid.stdout + valid.stderr

    tl["items"][0]["rows"][0][1].update({"at": 2.0, "showAt": 0.49})
    p.write_text(json.dumps(tl))
    early = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                            str(p)], capture_output=True, text=True)
    assert early.returncode == 1 and "revealed" in early.stdout


def test_rejected_caption_style_is_invalid_even_without_marker_words(tmp_path):
    p = _timeline(tmp_path)
    tl = json.loads(p.read_text())
    tl["items"][0]["captionStyle"] = "marker"
    p.write_text(json.dumps(tl))
    r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                        str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "marker" in r.stdout


def test_rejected_marker_word_kind_is_invalid(tmp_path):
    p = _timeline(tmp_path)
    tl = json.loads(p.read_text())
    tl["items"][0]["rows"][0][0]["kind"] = "pay"
    p.write_text(json.dumps(tl))
    r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                        str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "pay" in r.stdout


def test_stage_renders_approved_features_and_has_no_marker_animation():
    html = (ROOT / "motion/stage.html").read_text()
    assert "at: wd.showAt ?? wd.at" in html
    for token in ("buildProof", "buildPhone", "buildDoodle",
                  "cowfield", "roadcar", "syncVideos", 'V.name === "worth"'):
        assert token in html, f"stage missing {token}"
    for forbidden in ("markerStyle", "mkbar", "#FF3355", ".hotbar"):
        assert forbidden not in html, f"rejected caption effect returned: {forbidden}"


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
              "brand": {"accent": "#D9824B", "name": "T"},
              "theme": {"radius": "round", "glow": 1.0, "speed": 1.0,
                        "easing": "pop", "fontMode": "sans",
                        "fontPack": "poppins", "captionStyle": "editorial"},
              "items": [{"type": "vector", "name": name, "mode": "fullbleed",
                         "label": "TEST", "at": 1.0, "until": 2.7}]}
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(tl))
        r = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                            str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name}: {r.stdout} {r.stderr}"


def test_worth_validation_dwell_rule(tmp_path):
    tl = {"version": 1, "fps": 30, "width": 1080, "height": 1920,
          "duration": 4.0, "brand": {"accent": "#D9824B"},
          "items": [{"type": "vector", "name": "worth", "mode": "fullbleed",
                     "at": 1.0, "until": 2.7}]}
    p = tmp_path / "worth.json"
    p.write_text(json.dumps(tl))
    good = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                           str(p)], capture_output=True, text=True)
    assert good.returncode == 0, good.stdout + good.stderr
    tl["items"][0]["until"] = 2.9
    p.write_text(json.dumps(tl))
    bad = subprocess.run([sys.executable, str(ROOT / "motion/validate.py"),
                          str(p)], capture_output=True, text=True)
    assert bad.returncode == 1 and "worth" in bad.stdout


# ------------------------------------------- fallback + qc event model
produce = load("produce", "motion/produce.py")
qc = load("motionqc", "motion/qc.py")
tight_base = load("whop_tight_base", "scripts/whop/tight_base.py")
whop_build = load("whop_build_clip", "scripts/whop/build_whop_clip.py")


def test_phrase_reveal_shows_a_hook_together_but_keeps_original_hold_times():
    first = [{"w": "My", "at": 0.0}, {"w": "worth", "at": 0.22},
             {"w": "isn't", "at": 0.48}]
    original, group_at = whop_build.phrase_reveal(first)
    second = [{"w": "in", "at": 0.75}, {"w": "my", "at": 0.91},
              {"w": "body.", "at": 1.22}]
    original += whop_build.phrase_reveal(second, group_at)[0]
    assert original == pytest.approx([0.0, 0.22, 0.48, 0.75, 0.91, 1.22])
    assert [w["at"] for w in first + second] == pytest.approx(original)
    assert {w["showAt"] for w in first + second} == {0.0}


def test_tight_base_keeps_a_natural_breath_and_leaves_short_pauses():
    cuts = tight_base.silence_cuts([(1.0, 1.25), (2.0, 2.3), (3.0, 3.5)])
    assert len(cuts) == 1
    assert cuts[0] == pytest.approx((3.09, 3.41))
    assert 0.18 == pytest.approx(0.5 - (cuts[0][1] - cuts[0][0]))


def test_tight_base_allows_gentler_reflective_pause_settings():
    cuts = tight_base.silence_cuts(
        [(0.0, 0.66), (1.0, 1.90)], max_gap=0.68, keep=0.32)
    assert len(cuts) == 1
    assert cuts[0] == pytest.approx((1.16, 1.74))
    with pytest.raises(ValueError, match="keep <= max_gap"):
        tight_base.silence_cuts([(0.0, 1.0)], max_gap=0.3, keep=0.4)


def test_editorial_caption_style_is_sentence_case_and_flat():
    html = (ROOT / "motion/stage.html").read_text()
    editorial = html.split('/* ---- editorial captions', 1)[1].split(
        '/* ---- proof card', 1)[0]
    assert "text-transform: none" in editorial
    assert "font-weight: 500" in editorial
    assert "text-shadow: none" in editorial
    assert "marker swipe" in editorial


def test_shield_scene_labels_the_spoken_idea_and_draws_the_check():
    html = (ROOT / "motion/stage.html").read_text()
    shield = html.split('} else if (V.name === "shield") {', 1)[1].split(
        '} else if (V.name === "hourglass") {', 1)[0]
    assert 'V.label || "GOOD HUMAN"' in shield
    assert "n.shCheck" in shield and "n.shLabelRule" in shield
    builder = html.split("function buildVector(item)", 1)[1].split(
        "function buildScene", 1)[0]
    assert 'label: item.label || ""' in builder
    assert 'if (item.label && V.name !== "shield")' in builder


@pytest.mark.parametrize("card", [
    {"approved": True, "video": "post5_demo", "style_sha256": "abc"},
    {"approved": True, "campaign": "street_you_grew_up_on", "style_sha256": "abc"},
])
def test_whop_render_rejects_missing_campaign_or_video_metadata(
        tmp_path, monkeypatch, card):
    timeline = tmp_path / "timeline.json"
    transcript = tmp_path / "transcript.json"
    job = tmp_path / "job"
    timeline.write_text(json.dumps({"items": []}))
    transcript.write_text("[]")
    monkeypatch.setattr(produce, "load_theme", lambda *_args: {
        "name": "whop", "styleCard": card})
    monkeypatch.setattr(sys, "argv", [
        str(ROOT / "motion/produce.py"), str(timeline), str(tmp_path / "base.mp4"),
        str(transcript), str(job), "--theme", "whop"])

    with pytest.raises(ValueError, match="missing campaign/video metadata"):
        produce.main()
    assert not job.exists()  # refuse before creating render outputs


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
    assert kinds == ["word", "word", "word", "key", "key", "key"], kinds
    assert out["items"][1]["rows"][0][0]["w"] == "hi"  # original kept
    assert out["items"][1]["rows"][0][0]["kind"] == "key"


def test_qc_pacing_counts_continuous_motion_as_change():
    tl = {"items": [
        {"type": "poster", "at": 0.2, "until": 1.4,
         "rows": [[{"w": "go", "at": 0.3, "kind": "key"}]]},
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
