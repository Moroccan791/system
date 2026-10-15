"""Automated QC: synthetic static/moving clips, hook and caption checks."""

import subprocess

import pytest

from clipper.ffmpeg import ffmpeg_exe
from clipper.qc import (check_first_caption, check_hook, check_static_shot,
                        parse_ass_events, run_qc)

ASS = """[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:10.00,Bar,,0,0,0,,{\\an7\\pos(0,0)}x
Dialogue: 1,0:00:00.40,0:00:02.00,Block,,0,0,0,,{\\an7\\pos(100,1500)\\fs84}HELLO WORLD
Dialogue: 1,0:00:02.10,0:00:04.00,Block,,0,0,0,,{\\an7\\pos(100,1500)\\fs84}AGAIN NOW
"""


@pytest.fixture(scope="module")
def ass_file(tmp_path_factory):
    p = tmp_path_factory.mktemp("qc") / "c.ass"
    p.write_text(ASS)
    return p


def _video(path, vf, seconds=6):
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"testsrc2=size=320x568:rate=30:duration={seconds}",
                    "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-an", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def static_video(tmp_path_factory):
    # a flat colour source: the background never changes, by construction
    path = tmp_path_factory.mktemp("qc") / "static.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=0x334455:size=320x568:rate=30:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                    str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def moving_video(tmp_path_factory):
    return _video(tmp_path_factory.mktemp("qc") / "moving.mp4", "null", 3)


def test_parse_ass_and_first_caption(ass_file):
    events = parse_ass_events(ass_file)
    blocks = [e for e in events if e["style"] == "Block"]
    assert blocks[0]["text"] == "HELLO WORLD" and blocks[0]["pos"] == (100.0, 1500.0)
    assert check_first_caption(events)["status"] == "pass"
    late = [dict(e, start=2.5) if e["style"] == "Block" else e for e in events]
    assert check_first_caption(late)["status"] == "fail"


def test_static_shot_detects_frozen_background(static_video, moving_video):
    assert check_static_shot(static_video)["status"] == "fail"
    assert check_static_shot(moving_video)["status"] == "pass"


def test_hook_check_flags_lead_ins_and_rewards_a_match():
    words = [{"text": "No", "start": 0.0}, {"text": "offense", "start": 0.2},
             {"text": "but", "start": 0.4}, {"text": "she", "start": 0.6},
             {"text": "lied", "start": 0.8}]
    r = check_hook(["HE NEVER CALLED BACK"], words)
    assert r["status"] == "fail"  # headline shares nothing with the opening

    words2 = [{"text": "She", "start": 0.0}, {"text": "lied", "start": 0.2},
              {"text": "to", "start": 0.4}, {"text": "him", "start": 0.55}]
    r2 = check_hook(["SHE LIED TO HIM"], words2)
    assert r2["status"] == "pass"


def test_run_qc_reports_every_check(moving_video, ass_file):
    report = run_qc(moving_video, ass=ass_file,
                    hook_lines=["SOMETHING HAPPENS"],
                    words=[{"text": "Something", "start": 0.0},
                           {"text": "happens", "start": 0.3}])
    names = {c["name"] for c in report["checks"]}
    assert names == {"first_caption", "caption_face", "static_shot",
                     "loudness", "hook_match", "duration", "logo_scan"}
    assert all(c["status"] in {"pass", "warn", "fail"} for c in report["checks"])
