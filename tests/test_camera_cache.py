"""Warm-camera cache — the 'find X' speed win (no real webcam)."""
import sys
import types

import numpy as np
import pytest


@pytest.fixture
def fake_cv2(monkeypatch):
    """Install a fake cv2 whose VideoCapture opens instantly and returns frames."""
    cv2 = types.ModuleType("cv2")
    cv2.CAP_DSHOW = 700
    cv2.CAP_ANY = 0

    class FakeCap:
        instances = 0

        def __init__(self, *a):
            FakeCap.instances += 1
            self._open = True

        def isOpened(self):
            return self._open

        def read(self):
            return True, np.zeros((4, 4, 3), dtype=np.uint8)

        def release(self):
            self._open = False

    cv2.VideoCapture = lambda *a: FakeCap()
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    return FakeCap


@pytest.fixture(autouse=True)
def _reset_cache():
    import backend.modules.vision.capture as cap
    cap.release_camera()
    yield
    cap.release_camera()


def test_snapshot_opens_and_caches(fake_cv2):
    import backend.modules.vision.capture as cap
    frame = cap.snapshot(0)
    assert frame.shape == (4, 4, 3)
    assert cap._cached_cam is not None and cap._cached_cam.is_open()


def test_second_snapshot_reuses_camera(fake_cv2):
    import backend.modules.vision.capture as cap
    cap.snapshot(0)
    first = cap._cached_cam
    opened_after_first = fake_cv2.instances
    cap.snapshot(0)
    # Same cached object, no new VideoCapture created on the warm path.
    assert cap._cached_cam is first
    assert fake_cv2.instances == opened_after_first


def test_release_camera_clears_cache(fake_cv2):
    import backend.modules.vision.capture as cap
    cap.snapshot(0)
    cap.release_camera()
    assert cap._cached_cam is None


def test_switching_device_reopens(fake_cv2):
    import backend.modules.vision.capture as cap
    cap.snapshot(0)
    n0 = fake_cv2.instances
    cap.snapshot(1)      # different device → must open a new capture
    assert fake_cv2.instances == n0 + 1
    assert cap._cached_device == 1
