"""The two things that stopped the chain running on a machine that was not the
author's: a hardcoded interpreter path, and a library path exported
unconditionally. Both are now looked up, so these tests pin that down.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------
def test_the_interpreter_is_the_one_running_us():
    from scripts.whop import runtime

    assert Path(runtime.python_exe()) == Path(sys.executable)


def test_no_script_names_an_interpreter_by_directory():
    """`.venv/bin/python` only exists on one computer.

    Every subprocess the whop chain starts used to name the interpreter that
    way, so the chain ran on the author's box and nowhere else — including the
    sandbox, where the environment is called `venv`.
    """
    offenders = []
    for p in Path("scripts/whop").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines():
            # docstrings may mention a path in prose; code may not use one
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue
            if '.venv/bin/python' in line and ('Path' in line or 'PY =' in line
                                               or '"' in line and 'python' in line
                                               and 'subprocess' in line):
                offenders.append(f"{p}: {stripped}")
    assert not offenders, "hardcoded interpreter: " + "; ".join(offenders)


def test_the_alsa_path_is_exported_only_when_it_exists():
    from scripts.whop import runtime

    env = runtime.render_env()
    if runtime.ALSA_LIB.is_dir():
        assert env.get("LD_LIBRARY_PATH") == str(runtime.ALSA_LIB)
    else:
        assert "LD_LIBRARY_PATH" not in env


def test_a_stale_alsa_path_is_removed_not_inherited():
    """A missing LD_LIBRARY_PATH entry can be fatal to some binaries."""
    from scripts.whop import runtime

    if runtime.ALSA_LIB.is_dir():
        pytest.skip("this machine has the ALSA runtime")
    base = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/does-not-exist"}
    assert "LD_LIBRARY_PATH" not in runtime.render_env(base)
    assert base["LD_LIBRARY_PATH"] == "/tmp/does-not-exist"      # not mutated


def test_missing_deps_reports_the_pip_name(capsys=None):
    from scripts.whop import runtime

    names = {pip for _mod, pip in runtime.missing_deps()}
    assert names <= set(runtime.NEEDED.values())
    # what is present must not be reported missing
    for mod, pip_name in runtime.NEEDED.items():
        try:
            __import__(mod)
        except Exception:
            assert pip_name in names or mod in {m for m, _ in runtime.missing_deps()}


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def test_doctor_blocks_when_the_transcript_is_gone(tmp_path):
    """The normal state after a reset: no work/, so no transcript."""
    from scripts.whop import doctor

    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({
        "post": "post6",
        "source": "work/street/raw_parts/does_not_exist_006.mp4",
        "transcript": "work/street/asr/does_not_exist_transcript.json",
    }))
    rep = doctor.Report()
    got = doctor.check_plan(rep, plan)
    assert got is not None
    doctor.check_source(rep, got)
    doctor.check_transcript(rep, got)

    blocking = {c.name for c in rep.blocking}
    assert "source footage" in blocking
    assert "transcript" in blocking
    # and each one says how to fix it
    for c in rep.blocking:
        assert c.fix, f"{c.name} blocks without saying what to do"


def test_doctor_passes_a_post_that_is_all_there(tmp_path):
    from scripts.whop import doctor

    src = tmp_path / "part.mp4"
    src.write_bytes(b"\0" * 16)
    tr = tmp_path / "t.json"
    tr.write_text(json.dumps({"words": [{"text": "hi", "start": 0, "end": 1}]}))
    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({"post": "postX", "source": str(src),
                                "transcript": str(tr)}))
    rep = doctor.Report()
    got = doctor.check_plan(rep, plan)
    doctor.check_source(rep, got)
    doctor.check_transcript(rep, got)
    assert not rep.blocking, [c.line() for c in rep.blocking]


def test_a_new_campaign_is_told_what_it_still_needs():
    from scripts.whop import doctor

    rep = doctor.Report()
    doctor.check_new_campaign(rep, "a_campaign_that_does_not_exist_yet")
    names = {c.name for c in rep.checks}
    assert "campaign" in names
    assert any(c.state == doctor.BLOCK for c in rep.checks)


def test_the_fetch_request_matches_the_workflow_contract(tmp_path, monkeypatch):
    """fetch.yml reads tag / pattern / out_dir. Get a key wrong and CI pulls
    nothing and says nothing."""
    from scripts.whop import doctor

    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    p = doctor.write_fetch_request("part_006.mp4", "footage-demi-1", "work/fetch")
    req = json.loads(p.read_text())
    assert set(req) == {"tag", "pattern", "out_dir"}
    assert p == tmp_path / ".github" / "footage-request.json"
