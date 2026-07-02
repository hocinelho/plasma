"""Tests for PA-100/101 — vision skill + VisionMonitor (all I/O mocked)."""
from __future__ import annotations
import sys
import time
import types
from unittest.mock import MagicMock, patch, call
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


_DETECTIONS = [
    {"label": "person", "score": 0.92, "box": [10, 20, 100, 200]},
    {"label": "laptop", "score": 0.78, "box": [200, 100, 150, 100]},
]


def _mock_cam(frame=None):
    """Return a fake LocalCameraCapture instance."""
    cam = MagicMock()
    cam.open.return_value = None
    cam.capture_frame.return_value = frame if frame is not None else _fake_frame()
    cam.close.return_value = None
    cam.__enter__ = lambda s: s
    cam.__exit__ = MagicMock(return_value=False)
    return cam


# ---------------------------------------------------------------------------
# Vision skill: snapshot
# ---------------------------------------------------------------------------

def test_vision_what_do_you_see():
    from backend.skills.vision import run
    with patch("backend.skills.vision._detect_from_local_camera", return_value=_DETECTIONS):
        result = run({"utterance": "what do you see"})
    assert "person" in result.lower()
    assert "laptop" in result.lower()


def test_vision_de_snapshot():
    from backend.skills.vision import run
    with patch("backend.skills.vision._detect_from_local_camera", return_value=_DETECTIONS):
        result = run({"utterance": "was siehst du", "language": "de"})
    assert "person" in result.lower() or "sehe" in result.lower()


def test_vision_no_detections():
    from backend.skills.vision import run
    with patch("backend.skills.vision._detect_from_local_camera", return_value=[]):
        result = run({"utterance": "what do you see"})
    assert "don't see" in result.lower() or "nothing" in result.lower() or "recognizable" in result.lower()


def test_vision_camera_unavailable():
    from backend.skills.vision import run
    with patch("backend.skills.vision._detect_from_local_camera", side_effect=RuntimeError("no cam")):
        result = run({"utterance": "what do you see"})
    assert "not available" in result.lower() or "camera" in result.lower()


def test_vision_mediapipe_missing():
    from backend.skills.vision import run
    with patch("backend.skills.vision._detect_from_local_camera", side_effect=ImportError("mediapipe not installed")):
        result = run({"utterance": "what do you see"})
    assert "mediapipe" in result.lower() or "install" in result.lower() or "missing" in result.lower()


def test_vision_limits_to_5_labels():
    from backend.skills.vision import run
    many = [{"label": f"obj{i}", "score": 0.9, "box": [0, 0, 10, 10]} for i in range(10)]
    with patch("backend.skills.vision._detect_from_local_camera", return_value=many):
        result = run({"utterance": "what do you see"})
    count = sum(1 for i in range(10) if f"obj{i}" in result)
    assert count <= 5


# ---------------------------------------------------------------------------
# Vision skill: monitor commands (patch vision_monitor in skill namespace)
# ---------------------------------------------------------------------------

def test_vision_watch_for_starts_monitor():
    from backend.skills import vision as vision_mod
    mock_monitor = MagicMock()
    with patch.object(vision_mod, "vision_monitor", mock_monitor):
        result = vision_mod.run({"utterance": "watch for a person", "session_id": "sess1"})
    mock_monitor.start_watching.assert_called_once()
    args = mock_monitor.start_watching.call_args[0]
    assert "person" in args[2]
    assert "watching" in result.lower() or "ausschau" in result.lower()


def test_vision_watch_for_de():
    from backend.skills import vision as vision_mod
    mock_monitor = MagicMock()
    with patch.object(vision_mod, "vision_monitor", mock_monitor):
        result = vision_mod.run({"utterance": "halte ausschau nach einer person", "language": "de"})
    mock_monitor.start_watching.assert_called_once()


def test_vision_stop_watching():
    from backend.skills import vision as vision_mod
    mock_monitor = MagicMock()
    with patch.object(vision_mod, "vision_monitor", mock_monitor):
        result = vision_mod.run({"utterance": "stop watching"})
    mock_monitor.stop_watching.assert_called_once()
    assert "stopped" in result.lower() or "gestoppt" in result.lower()


def test_vision_stop_watching_de():
    from backend.skills import vision as vision_mod
    mock_monitor = MagicMock()
    with patch.object(vision_mod, "vision_monitor", mock_monitor):
        result = vision_mod.run({"utterance": "hör auf zu beobachten", "language": "de"})
    mock_monitor.stop_watching.assert_called_once()


def test_vision_monitor_error_returns_message():
    from backend.skills import vision as vision_mod
    mock_monitor = MagicMock()
    mock_monitor.start_watching.side_effect = RuntimeError("cam busy")
    with patch.object(vision_mod, "vision_monitor", mock_monitor):
        result = vision_mod.run({"utterance": "watch for a dog"})
    assert "camera" in result.lower() or "not available" in result.lower()


# ---------------------------------------------------------------------------
# VisionMonitor: unit tests (patch at module level so thread picks them up)
# ---------------------------------------------------------------------------

def test_vision_monitor_enabled_after_start():
    from backend.modules.vision import monitor as mon_mod
    from backend.modules.vision.monitor import VisionMonitor

    vm = VisionMonitor()
    mock_ptts = MagicMock()
    mock_det = MagicMock()
    mock_det.detect.return_value = []
    mock_cam_inst = _mock_cam()

    with patch.object(mon_mod, "get_detector", return_value=mock_det), \
         patch.object(mon_mod, "LocalCameraCapture", return_value=mock_cam_inst), \
         patch.object(mon_mod, "proactive_tts", mock_ptts):
        vm.start_watching("sess", "en", ["person"])
        assert vm.enabled
        vm.stop_watching()
        assert not vm.enabled


def test_vision_monitor_fires_proactive_tts():
    """When a watched object is detected, proactive_tts.fire() must be called."""
    from backend.modules.vision import monitor as mon_mod
    from backend.modules.vision.monitor import VisionMonitor

    fired_events = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired_events.append((text, lang))

    mock_det = MagicMock()
    mock_det.detect.return_value = [{"label": "person", "score": 0.9, "box": [0, 0, 100, 100]}]
    mock_cam_inst = _mock_cam()

    vm = VisionMonitor()

    with patch.object(mon_mod, "get_detector", return_value=mock_det), \
         patch.object(mon_mod, "LocalCameraCapture", return_value=mock_cam_inst), \
         patch.object(mon_mod, "proactive_tts", mock_ptts):
        vm.start_watching("sess", "en", ["person"], alert_cooldown_s=0, fps=20.0)
        time.sleep(0.3)
        vm.stop_watching()

    assert len(fired_events) > 0, "ProactiveTTS should have been fired"
    assert any("person" in t.lower() for t, _ in fired_events)


def test_vision_monitor_only_alerts_watched_labels():
    """Objects not in watch_for must not trigger alerts."""
    from backend.modules.vision import monitor as mon_mod
    from backend.modules.vision.monitor import VisionMonitor

    fired_events = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired_events.append((text, lang))

    mock_det = MagicMock()
    mock_det.detect.return_value = [{"label": "dog", "score": 0.9, "box": [0, 0, 100, 100]}]
    mock_cam_inst = _mock_cam()

    vm = VisionMonitor()

    with patch.object(mon_mod, "get_detector", return_value=mock_det), \
         patch.object(mon_mod, "LocalCameraCapture", return_value=mock_cam_inst), \
         patch.object(mon_mod, "proactive_tts", mock_ptts):
        vm.start_watching("sess", "en", ["person"], alert_cooldown_s=0, fps=20.0)
        time.sleep(0.2)
        vm.stop_watching()

    assert len(fired_events) == 0, "Dog must NOT alert when watching for person"


def test_vision_monitor_cooldown_prevents_repeat_alert():
    """Same label must not fire twice within cooldown window."""
    from backend.modules.vision import monitor as mon_mod
    from backend.modules.vision.monitor import VisionMonitor

    fired_events = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired_events.append((text, lang))

    mock_det = MagicMock()
    mock_det.detect.return_value = [{"label": "person", "score": 0.9, "box": [0, 0, 100, 100]}]
    mock_cam_inst = _mock_cam()

    vm = VisionMonitor()

    with patch.object(mon_mod, "get_detector", return_value=mock_det), \
         patch.object(mon_mod, "LocalCameraCapture", return_value=mock_cam_inst), \
         patch.object(mon_mod, "proactive_tts", mock_ptts):
        # cooldown_s=60 → only first detection should alert
        vm.start_watching("sess", "en", ["person"], alert_cooldown_s=60.0, fps=20.0)
        time.sleep(0.3)
        vm.stop_watching()

    assert len(fired_events) == 1, "With 60s cooldown, only one alert should fire"


# ---------------------------------------------------------------------------
# ObjectDetector: unit test (mock mediapipe via sys.modules)
# ---------------------------------------------------------------------------

def test_detector_detect_returns_list():
    """ObjectDetector.detect() returns a list of dicts when mediapipe is mocked."""
    # Build a minimal mediapipe mock
    mp_mock = types.ModuleType("mediapipe")
    mp_tasks = types.ModuleType("mediapipe.tasks")
    mp_python = types.ModuleType("mediapipe.tasks.python")
    mp_vision_mod = types.ModuleType("mediapipe.tasks.python.vision")

    # Detection result mock
    cat = MagicMock()
    cat.category_name = "cup"
    cat.score = 0.85
    det = MagicMock()
    det.categories = [cat]
    det.bounding_box.origin_x = 10
    det.bounding_box.origin_y = 20
    det.bounding_box.width = 50
    det.bounding_box.height = 60
    det_result = MagicMock()
    det_result.detections = [det]

    mock_mp_det_inst = MagicMock()
    mock_mp_det_inst.detect.return_value = det_result

    mock_det_cls = MagicMock()
    mock_det_cls.create_from_options.return_value = mock_mp_det_inst

    mp_vision_mod.ObjectDetector = mock_det_cls
    mp_vision_mod.ObjectDetectorOptions = MagicMock()
    mp_vision_mod.RunningMode = MagicMock()

    mp_python.BaseOptions = MagicMock()

    mp_mock.tasks = mp_tasks
    mp_tasks.python = mp_python

    mp_image_inst = MagicMock()
    mp_mock.Image = MagicMock(return_value=mp_image_inst)
    mp_mock.ImageFormat = MagicMock()
    mp_mock.ImageFormat.SRGB = "SRGB"

    sys_modules_patch = {
        "mediapipe": mp_mock,
        "mediapipe.tasks": mp_tasks,
        "mediapipe.tasks.python": mp_python,
        "mediapipe.tasks.python.vision": mp_vision_mod,
    }

    from backend.modules.vision.detector import ObjectDetector

    detector = ObjectDetector(score_threshold=0.5)
    detector._detector = mock_mp_det_inst  # bypass _load()

    with patch.dict(sys.modules, sys_modules_patch):
        # Monkey-patch the mp module reference inside detector.py
        import backend.modules.vision.detector as det_mod
        original_mp = getattr(det_mod, "mp_mod", None)
        # The detect() method imports mediapipe inline via `import mediapipe as mp`
        # We set _detector directly so _load() is skipped; only `mp.Image(...)` matters
        with patch.dict(sys.modules, sys_modules_patch):
            result = detector.detect(_fake_frame())

    # Even if the mp.Image call is mocked, our mock_mp_det_inst.detect returns det_result
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Capture: unit tests (mock cv2 via sys.modules)
# ---------------------------------------------------------------------------

_AUTO = object()  # sentinel

def _build_cv2_mock(decode_result=_AUTO):
    """Return a minimal cv2 mock for capture tests. No real cv2 needed."""
    cv2_mock = types.ModuleType("cv2")
    cv2_mock.IMREAD_COLOR = 1

    fake_frame = _fake_frame()

    cap_inst = MagicMock()
    cap_inst.isOpened.return_value = True
    cap_inst.read.return_value = (True, fake_frame)
    cv2_mock.VideoCapture = MagicMock(return_value=cap_inst)

    cv2_mock.imdecode = MagicMock(return_value=fake_frame if decode_result is _AUTO else decode_result)

    return cv2_mock


def test_local_camera_capture_open_close():
    from backend.modules.vision.capture import LocalCameraCapture
    cv2_mock = _build_cv2_mock()
    with patch.dict(sys.modules, {"cv2": cv2_mock}):
        cam = LocalCameraCapture(device_index=0)
        cam.open()
        assert cam._cap is not None
        cam.close()
        assert cam._cap is None


def test_local_camera_capture_frame():
    from backend.modules.vision.capture import LocalCameraCapture
    cv2_mock = _build_cv2_mock()
    with patch.dict(sys.modules, {"cv2": cv2_mock}):
        cam = LocalCameraCapture(device_index=0)
        cam.open()
        frame = cam.capture_frame()
        cam.close()
    assert frame is not None
    assert frame.shape == (480, 640, 3)


def test_local_camera_capture_frame_retries_after_empty_reads():
    """Webcam returns failed/empty reads first, then a good frame — capture retries."""
    from backend.modules.vision.capture import LocalCameraCapture
    cv2_mock = _build_cv2_mock()
    good = _fake_frame()
    # First several reads fail (ret=False / None), then a real frame arrives.
    cap_inst = cv2_mock.VideoCapture.return_value
    cap_inst.read.side_effect = (
        [(False, None)] * 7 + [(True, good)] + [(True, good)] * 20
    )
    with patch.dict(sys.modules, {"cv2": cv2_mock}), \
         patch("backend.modules.vision.capture.time.sleep"):
        cam = LocalCameraCapture(device_index=0)
        cam.open()
        frame = cam.capture_frame()
        cam.close()
    assert frame is not None
    assert frame.shape == (480, 640, 3)


def test_decode_frame_bytes_valid():
    from backend.modules.vision.capture import decode_frame_bytes
    fake = _fake_frame()
    cv2_mock = _build_cv2_mock(decode_result=fake)
    with patch.dict(sys.modules, {"cv2": cv2_mock}):
        result = decode_frame_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
    assert result is not None
    assert result.shape == (480, 640, 3)


def test_decode_frame_bytes_invalid_raises():
    from backend.modules.vision.capture import decode_frame_bytes
    cv2_mock = _build_cv2_mock(decode_result=None)
    with patch.dict(sys.modules, {"cv2": cv2_mock}):
        with pytest.raises(ValueError, match="Could not decode"):
            decode_frame_bytes(b"not an image")


# ---------------------------------------------------------------------------
# Skill meta
# ---------------------------------------------------------------------------

def test_vision_self_test():
    from backend.skills.vision import self_test
    assert self_test()


def test_vision_meta():
    from backend.skills.vision import META
    assert META["name"] == "vision"
    assert any("what do you see" in t for t in META["triggers"])
    assert any("watch for" in t for t in META["triggers"])
    assert any("stop watching" in t for t in META["triggers"])


# ---------------------------------------------------------------------------
# Open-vocabulary recognition + appearance ("what am I wearing")
# ---------------------------------------------------------------------------

def test_vision_appearance_triggers_present():
    from backend.skills.vision import META
    for t in ["what am i wearing", "what is this", "was trage ich"]:
        assert t in META["triggers"]


def test_appearance_regex_matches():
    from backend.skills.vision import _APPEARANCE_RE
    assert _APPEARANCE_RE.search("what am i wearing")
    assert _APPEARANCE_RE.search("what color is my shirt")
    assert _APPEARANCE_RE.search("was trage ich heute")
    assert not _APPEARANCE_RE.search("what do you see")


def test_vision_uses_open_vocab_first():
    from backend.skills import vision as vision_mod
    with patch.object(vision_mod, "_recognize_open_vocab", return_value="I see a red mug and a laptop."):
        result = vision_mod.run({"utterance": "what do you see"})
    assert "red mug" in result.lower()


def test_vision_appearance_passes_utterance():
    from backend.skills import vision as vision_mod
    seen = {}

    def fake_reco(de, utterance=""):
        seen["utterance"] = utterance
        return "You're wearing a blue jacket."

    with patch.object(vision_mod, "_recognize_open_vocab", side_effect=fake_reco):
        result = vision_mod.run({"utterance": "what am I wearing"})
    assert "blue jacket" in result.lower()
    assert "wearing" in seen["utterance"].lower()


def test_vision_vlm_error_gives_helpful_message():
    from backend.skills import vision as vision_mod
    # VLM is configured but recognition returned nothing (model errored/500).
    with patch.object(vision_mod, "_recognize_open_vocab", return_value=None), \
         patch.object(vision_mod, "_vlm_configured", return_value=True):
        result = vision_mod.run({"utterance": "describe me"})
    assert "llava" in result.lower() or "lighter" in result.lower() or "too large" in result.lower()
