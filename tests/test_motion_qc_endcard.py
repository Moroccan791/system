from __future__ import annotations

import numpy as np
import cv2

from motion.qc import endcard_opaque


class FakeCapture:
    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.position = 0

    def isOpened(self) -> bool:
        return True

    def get(self, prop: int) -> float:
        if prop == cv2.CAP_PROP_FPS:
            return 30.0
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return 2.0
        return 0.0

    def set(self, _prop: int, value: float) -> bool:
        self.position = int(value)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        return (self.position == 0, self.frame.copy() if self.position == 0 else None)

    def release(self) -> None:
        pass


def _timeline() -> dict:
    return {"duration": 2 / 30,
            "items": [{"type": "endcard", "at": 0.0, "until": 2 / 30}]}


def test_endcard_background_passes_when_first_frame_is_opaque(monkeypatch, tmp_path):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: FakeCapture(frame))

    status, detail = endcard_opaque(tmp_path / "black.mp4", _timeline())

    assert status == "pass"
    assert "opaque" in detail


def test_endcard_background_fails_when_underlying_video_bleeds(monkeypatch, tmp_path):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Simulate a speaker frame showing through around the CTA copy.
    frame[:6, :, :] = 96
    frame[-6:, :, :] = 96
    frame[:, :6, :] = 96
    frame[:, -6:, :] = 96
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: FakeCapture(frame))

    status, detail = endcard_opaque(tmp_path / "bleed.mp4", _timeline())

    assert status == "fail"
    assert "possible footage under CTA" in detail
