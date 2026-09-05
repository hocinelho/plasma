"""She should look through the camera that is already open, not open another.

The bug this pins, measured on a real run: asking "can you see me?" while the
desktop overlay was watching took 46 seconds, and 21 of those were
cv2.VideoCapture trying to open webcam 0 through DirectShow while Chromium
still had it. The browser had been streaming decoded frames of that exact
camera to /ws/perception-input the whole time.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.vision import live_frame  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    live_frame.clear()
    yield
    live_frame.clear()


class TestTheStore:
    def test_nothing_stored_is_not_a_frame(self):
        assert live_frame.get() is None
        assert live_frame.age_s() is None

    def test_a_frame_just_in_comes_back(self):
        live_frame.put("frame")
        assert live_frame.get() == "frame"
        assert live_frame.age_s() < 1.0

    def test_a_stale_frame_is_refused(self):
        """A picture from a minute ago is not an answer to "what do you see
        NOW" — better to fall back to the webcam than to describe the past."""
        live_frame.put("old")
        assert live_frame.get(max_age_s=0.0) is None
        assert live_frame.get(max_age_s=60) == "old"

    def test_the_default_age_covers_a_gap_in_the_stream(self):
        """Frames arrive at VISION_FPS (6/s). The window has to tolerate a
        dropped frame or two without falling back to opening the device."""
        assert 1.0 <= live_frame.DEFAULT_MAX_AGE_S <= 5.0

    def test_a_newer_frame_replaces_the_last(self):
        live_frame.put("first")
        live_frame.put("second")
        assert live_frame.get() == "second"

    def test_clear_forgets_it(self):
        live_frame.put("frame")
        live_frame.clear()
        assert live_frame.get() is None

    def test_it_is_safe_to_write_from_the_websocket_and_read_from_a_skill(self):
        """The perception socket writes on the event loop; skills read on a
        worker thread. Torn state here would be a rare, unreproducible wrong
        answer."""
        import threading
        stop = time.monotonic() + 0.3
        errors: list = []

        def writer():
            while time.monotonic() < stop:
                live_frame.put(object())

        def reader():
            while time.monotonic() < stop:
                try:
                    live_frame.get()
                except Exception as e:      # pragma: no cover
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestSnapshotPrefersIt:
    def test_a_live_frame_means_the_device_is_never_opened(self, monkeypatch):
        """The whole point. If this regresses, the only symptom is that she
        gets slow again — no error, no wrong answer."""
        from backend.modules.vision import capture

        opened = []
        monkeypatch.setattr(capture, "LocalCameraCapture",
                            lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(
                                AssertionError("opened the camera")))
        live_frame.put("browser frame")
        assert capture.snapshot(0) == "browser frame"
        assert not opened

    def test_it_falls_back_to_the_camera_when_nothing_is_streaming(self, monkeypatch):
        """Without a browser watching, the local device is the only way to
        look — the preference must not become a refusal."""
        from backend.modules.vision import capture

        class _Cam:
            def __init__(self, *_a):
                pass

            def open(self):
                pass

            def settle(self, _s):
                pass

            def is_open(self):
                return True

            def capture_frame(self, warmup=0):
                return "device frame"

        monkeypatch.setattr(capture, "LocalCameraCapture", _Cam)
        monkeypatch.setattr(capture, "_cached_cam", None, raising=False)
        monkeypatch.setattr(capture, "_cached_device", None, raising=False)
        assert capture.snapshot(0) == "device frame"


class TestTheSocketFeedsIt:
    def test_the_perception_socket_stores_every_frame_it_decodes(self):
        """It already had the decoded frame in hand; the fix is one line
        there and nothing else changes about that loop."""
        src = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(
            encoding="utf-8")
        block = src.split("/ws/perception-input", 1)[1]
        assert "live_frame.put(frame)" in block

    def test_it_forgets_the_frame_when_the_browser_lets_go(self):
        """The camera is no longer being watched, so the last frame is no
        longer what she can see."""
        src = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(
            encoding="utf-8")
        block = src.split("Perception-input WS client disconnected", 1)[0]
        assert "live_frame.clear()" in block[-1200:]
