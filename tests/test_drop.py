"""Stage 0 fallback: collecting footage pushed to a git branch."""
from __future__ import annotations

import subprocess

import pytest

from clipper.ingest import drop


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def test_a_shorts_download_is_a_reference():
    folder, why = drop.classify_drop(
        "YTDown.com_Shorts_Media_mGG7OEATpkk_80-Of-Men-Aren-t-Going-To-Succeed_001_1080p.mp4")
    assert folder == "references"
    assert "short" in why


def test_a_plain_youtube_download_is_raw_footage():
    folder, why = drop.classify_drop(
        "YTDown.com_YouTube_Media_XrdXKjTOQBg_Women-Are-Shocked-By-The-Reality-Of-Dating_002_720p.mp4")
    assert folder == "raw"
    assert "youtube" in why


def test_an_unhelpful_name_falls_back_to_length():
    assert drop.classify_drop("clip-1.mp4", 42.0)[0] == "references"
    assert drop.classify_drop("clip-2.mp4", 3600.0)[0] == "raw"
    assert drop.classify_drop("clip-3.mp4", None)[0] == "raw"     # cannot tell -> raw
    assert "short enough" in drop.classify_drop("clip-1.mp4", 42.0)[1]


def test_the_name_beats_the_length():
    """A long download that says "shorts" is still meant as an example."""
    assert drop.classify_drop("Some_Shorts_thing.mp4", 900.0)[0] == "references"


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def _files(tmp_path, *names, size=64):
    made = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"x" * size)
        made.append(path)
    return made


def test_plan_sorts_files_into_the_two_folders(tmp_path):
    files = _files(tmp_path, "a_Shorts_1.mp4", "b_YouTube_1.mp4")
    planned = drop.plan_moves(files, tmp_path / "camp", duration_lookup=lambda p: None)
    assert [p["dest"].parent.name for p in planned] == ["references", "raw"]
    assert planned[0]["action"] == "copy"


def test_plan_does_not_copy_a_file_that_is_already_there(tmp_path):
    files = _files(tmp_path, "a_Shorts_1.mp4")
    campaign = tmp_path / "camp"
    first = drop.plan_moves(files, campaign, duration_lookup=lambda p: None)
    drop.copy_planned(first)
    again = drop.plan_moves(files, campaign, duration_lookup=lambda p: None)
    assert again[0]["action"] == "already there"
    assert drop.copy_planned(again)[0]["action"] == "already there"


def test_plan_refuses_to_clobber_a_different_file_of_the_same_name(tmp_path):
    files = _files(tmp_path, "a_Shorts_1.mp4", size=64)
    campaign = tmp_path / "camp"
    drop.copy_planned(drop.plan_moves(files, campaign, duration_lookup=lambda p: None))
    files[0].write_bytes(b"y" * 999)          # same name, new content
    planned = drop.plan_moves(files, campaign, duration_lookup=lambda p: None)
    assert planned[0]["action"] == "name taken"
    assert (campaign / "references" / "a_Shorts_1.mp4").stat().st_size == 64
    forced = drop.plan_moves(files, campaign, duration_lookup=lambda p: None, overwrite=True)
    assert forced[0]["action"] == "copy"


def test_two_files_with_one_name_do_not_overwrite_each_other(tmp_path):
    one = tmp_path / "one" / "clip.mp4"
    two = tmp_path / "two" / "clip.mp4"
    for path in (one, two):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * 32)
    planned = drop.plan_moves([one, two], tmp_path / "camp", duration_lookup=lambda p: None)
    assert len({p["dest"].name for p in planned}) == 2


def test_into_forces_every_file_into_one_folder(tmp_path):
    files = _files(tmp_path, "a_Shorts_1.mp4", "b_YouTube_1.mp4")
    planned = drop.plan_moves(files, tmp_path / "camp", into="raw",
                              duration_lookup=lambda p: None)
    assert {p["dest"].parent.name for p in planned} == {"raw"}
    assert planned[0]["why"] == "you said so"


def test_dry_run_writes_nothing(tmp_path):
    files = _files(tmp_path, "a_Shorts_1.mp4")
    campaign = tmp_path / "camp"
    planned = drop.plan_moves(files, campaign, duration_lookup=lambda p: None)
    drop.copy_planned(planned, dry_run=True)
    assert not (campaign / "references" / "a_Shorts_1.mp4").exists()


# --------------------------------------------------------------------------- #
# git plumbing
# --------------------------------------------------------------------------- #
def _fake_push(tmp_path, files: dict[str, bytes], branch: str = "footage"):
    """A repo with those files committed on a branch, usable as an origin."""
    origin = tmp_path / "origin"
    origin.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(origin), *a], check=True,
                                    capture_output=True, text=True)
    run("init", "-q", "-b", "main", ".")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "test")
    for name, blob in files.items():
        path = origin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    run("add", "-f", ".")
    run("commit", "-qm", "footage")
    run("branch", branch)
    return origin


def test_fetched_files_pulls_the_media_out_of_a_branch(tmp_path):
    origin = _fake_push(tmp_path, {
        "coming-in/a_Shorts_1.mp4": b"x" * 10,
        "coming-in/b_YouTube_1.mp4": b"x" * 10,
        "notes.txt": b"ignore me",
    })
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(origin)], check=True)

    with drop.fetched_files(repo, "footage") as files:
        assert sorted(p.name for p in files) == ["a_Shorts_1.mp4", "b_YouTube_1.mp4"]
        # the plan can be carried out while the files are still on disk
        planned = drop.plan_moves(files, repo / "camp", duration_lookup=lambda p: None)
        drop.copy_planned(planned)
    assert (repo / "camp" / "references" / "a_Shorts_1.mp4").exists()


def test_a_branch_that_does_not_exist_is_reported_not_crashed(tmp_path):
    origin = _fake_push(tmp_path, {"a.mp4": b"x"})
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(origin)], check=True)
    assert drop.branch_exists(repo, "footage") is True
    assert drop.branch_exists(repo, "nope") is False
    assert drop.branch_exists(repo, "main") is True


def test_the_how_to_text_points_at_the_real_repo(monkeypatch):
    text = drop.HOW_TO_SEND.format(slug="Moroccan791/system", branch="footage",
                                   campaign="michael_sartain")
    assert "https://github.com/Moroccan791/system" in text
    assert "clip" in text and "--branch footage" in text


def test_remote_slug_reads_https_and_ssh_remotes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "."], check=True)
    for url in ("https://github.com/Moroccan791/system.git",
                "git@github.com:Moroccan791/system.git"):
        subprocess.run(["git", "-C", str(repo), "remote", "remove", "origin"],
                       check=False, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)
        assert drop.remote_slug(repo) == "Moroccan791/system"
