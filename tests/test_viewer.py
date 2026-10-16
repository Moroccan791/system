"""The viewer is the only way to actually watch what the pipeline produced."""
from __future__ import annotations

import json

import pytest

from clipper import config
from clipper.serve import viewer


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A miniature workspace: one campaign, one raw file, one rendered edit."""
    root = tmp_path / "ws"
    for name in ("campaigns", "samples", "styles", "output", "work"):
        (root / name).mkdir(parents=True, exist_ok=True)
    raw = root / "campaigns" / "demo" / "raw"
    raw.mkdir(parents=True)
    (raw / "talk.mp4").write_bytes(b"\x00" * 2048)
    edits = root / "work" / "demo" / "edits"
    edits.mkdir(parents=True)
    (edits / "talk_01.mp4").write_bytes(b"\x00" * 4096)
    (edits / "talk_01.plan.json").write_text(json.dumps({
        "version": 1, "campaign": "demo",
        "clip": {"id": "#01", "source": str(raw / "talk.mp4"), "start": 0.5,
                 "end": 8.5, "duration": 8.0, "score": 0.7, "reasons": ["a hook"]},
        "target": {"platform": "tiktok", "width": 1080, "height": 1920, "fps": 30},
        "style": {"avg_shot_len": 2.0, "zoom": "punch_in", "transition": "cut"},
        "shots": [{"index": 1, "start": 0.5, "end": 2.5, "duration": 2.0,
                   "zoom": {"type": "punch_in"}, "transition": "cut"},
                  {"index": 2, "start": 2.5, "end": 8.5, "duration": 6.0,
                   "zoom": {"type": "static"}, "transition": "cut"}],
        "captions": {"words": 0, "window": [0.5, 8.5]}, "notes": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "ROOT", root)
    for attr in ("CAMPAIGNS", "SAMPLES", "STYLES", "OUTPUT", "WORK"):
        monkeypatch.setattr(config, attr, root / attr.lower())
    monkeypatch.setattr(viewer.config, "ROOT", root)
    return root


def test_viewer_shows_rendered_edits_with_their_plan(workspace):
    page = viewer.build_index(workspace)
    assert "/media/work/demo/edits/talk_01.mp4" in page
    assert "#01 · 8.0s · 2 shots" in page
    assert "punch_in · cut · 1080x1920 · tiktok" in page
    assert "shots 2.00s 6.00s" in page
    assert "/media/work/demo/edits/talk_01.plan.json" in page
    assert "Assembled clips" in page


def test_viewer_lists_raw_footage_so_it_can_be_watched(workspace):
    page = viewer.build_index(workspace)
    assert "/media/campaigns/demo/raw/talk.mp4" in page
    assert "raw · talk.mp4" in page


def test_edits_are_not_listed_twice(workspace):
    """The dedicated section replaces the generic work-file listing for them."""
    page = viewer.build_index(workspace)
    assert page.count('src="/media/work/demo/edits/talk_01.mp4"') == 1


def test_viewer_handles_an_empty_workspace(tmp_path, monkeypatch):
    root = tmp_path / "empty"
    root.mkdir()
    monkeypatch.setattr(viewer.config, "ROOT", root)
    for attr in ("CAMPAIGNS", "SAMPLES", "STYLES", "OUTPUT", "WORK"):
        monkeypatch.setattr(viewer.config, attr, root / attr.lower())
    page = viewer.build_index(root)
    assert "No campaigns found" in page


# ---------------------------------------------------------------------------
# the HTTP side: preview proxies and <video> probe with HEAD and Range
# ---------------------------------------------------------------------------
@pytest.fixture
def live(workspace):
    """The real handler on a real socket - the only way to test the wire."""
    from http.server import ThreadingHTTPServer
    import threading

    handler = type("BoundViewer", (viewer.ViewerHandler,), {"root": workspace})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _request(url, method="GET", headers=None):
    import urllib.request

    req = urllib.request.Request(url, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, dict(response.headers), response.read()


def test_responses_are_http_1_1_so_players_can_reuse_the_connection(live):
    status, headers, _ = _request(f"{live}/health")
    assert status == 200
    assert headers["Server"].startswith("clipper-viewer")


def test_head_requests_are_answered(live):
    """A 501 here is what makes a preview look dead: HEAD is how it is probed."""
    status, headers, body = _request(f"{live}/", method="HEAD")
    assert status == 200
    assert int(headers["Content-Length"]) > 0
    assert body == b""
    status, _, body = _request(f"{live}/health", method="HEAD")
    assert status == 200 and body == b""


def test_head_on_a_video_reports_its_size_without_sending_it(live, workspace):
    clip = workspace / "work" / "demo" / "edits" / "talk_01.mp4"
    status, headers, body = _request(f"{live}/media/work/demo/edits/talk_01.mp4", method="HEAD")
    assert status == 200
    assert body == b""
    assert int(headers["Content-Length"]) == clip.stat().st_size
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["Content-Type"] == "video/mp4"


def test_range_requests_serve_exactly_the_bytes_asked_for(live, workspace):
    """Seeking in <video> is Range requests; without 206 it restarts from zero."""
    clip = workspace / "work" / "demo" / "edits" / "talk_01.mp4"
    raw = clip.read_bytes()
    status, headers, body = _request(
        f"{live}/media/work/demo/edits/talk_01.mp4", headers={"Range": "bytes=100-199"})
    assert status == 206
    assert headers["Content-Range"] == f"bytes 100-199/{len(raw)}"
    assert body == raw[100:200]
    # players also ask for the tail ("bytes=-N") to read metadata
    status, headers, body = _request(
        f"{live}/media/work/demo/edits/talk_01.mp4", headers={"Range": "bytes=-50"})
    assert status == 206 and len(body) == 50 and body == raw[-50:]


def test_whole_file_downloads_match_the_file_on_disk(live, workspace):
    clip = workspace / "work" / "demo" / "edits" / "talk_01.mp4"
    status, _, body = _request(f"{live}/media/work/demo/edits/talk_01.mp4")
    assert status == 200
    assert body == clip.read_bytes()


def test_missing_files_are_404_for_both_methods(live):
    import urllib.error

    for method in ("GET", "HEAD"):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _request(f"{live}/media/nope.mp4", method=method)
        assert excinfo.value.code == 404
