"""Tests for the YOLO-ONNX detector backend (pre/post-processing + factory).

No model file or onnxruntime session needed: decode_predictions, nms,
letterbox, and parse_names are pure; the factory is tested via config."""
import numpy as np

from backend.modules.vision.yolo_onnx import (
    YoloOnnxDetector,
    decode_predictions,
    letterbox,
    nms,
    parse_names,
)

NAMES = ["pen", "mouse", "bottle"]


def _raw(candidates, nc=3, n=8, extra=0, orient="cn"):
    """Build a fake Ultralytics output [1, 4+nc+extra, n] (or transposed).

    candidates: list of (cx, cy, w, h, class_id, score); remaining slots are
    near-zero background.
    """
    arr = np.zeros((4 + nc + extra, n), dtype=np.float32)
    arr[0:4, :] = 1.0  # harmless tiny boxes for background slots
    for i, (cx, cy, w, h, cid, score) in enumerate(candidates):
        arr[0:4, i] = [cx, cy, w, h]
        arr[4 + cid, i] = score
    if orient == "nc":
        arr = arr.T
    return arr[None]


def test_parse_names_dict_and_list():
    assert parse_names("{0: 'pen', 1: 'mouse'}") == ["pen", "mouse"]
    assert parse_names("['pen', 'mouse']") == ["pen", "mouse"]
    assert parse_names("") == []
    assert parse_names("not python") == []


def test_decode_basic_detection():
    raw = _raw([(100, 80, 40, 20, 0, 0.9)])
    out = decode_predictions(raw, NAMES, 0.5, gain=1.0, pad=(0, 0), orig_hw=(640, 640))
    assert len(out) == 1
    d = out[0]
    assert d["label"] == "pen"
    assert d["score"] == 0.9
    assert d["box"] == [80.0, 70.0, 40.0, 20.0]  # cxcywh → xywh


def test_decode_transposed_and_seg_layouts():
    """[1, N, C] order and seg exports (+32 mask coeff rows) both decode."""
    for kwargs in ({"orient": "nc"}, {"extra": 32}):
        raw = _raw([(100, 80, 40, 20, 2, 0.8)], **kwargs)
        out = decode_predictions(raw, NAMES, 0.5, 1.0, (0, 0), (640, 640))
        assert len(out) == 1 and out[0]["label"] == "bottle"


def test_decode_undoes_letterbox():
    """A box in letterboxed coords maps back to original-frame pixels."""
    # gain 0.5, pad (0, 140): a 1280x720 frame letterboxed into 640x640.
    raw = _raw([(320, 320, 100, 100, 1, 0.9)])
    out = decode_predictions(raw, NAMES, 0.5, gain=0.5, pad=(0, 140), orig_hw=(720, 1280))
    (x, y, w, h) = out[0]["box"]
    assert (x, y, w, h) == (540.0, 260.0, 200.0, 200.0)


def test_decode_threshold_filters_weak():
    raw = _raw([(100, 80, 40, 20, 0, 0.3)])
    assert decode_predictions(raw, NAMES, 0.5, 1.0, (0, 0), (640, 640)) == []


def test_decode_nms_dedupes_same_object():
    """Two near-identical boxes of the same class collapse to one."""
    raw = _raw([(100, 80, 40, 20, 0, 0.9), (102, 81, 40, 20, 0, 0.7)])
    out = decode_predictions(raw, NAMES, 0.5, 1.0, (0, 0), (640, 640))
    assert len(out) == 1 and out[0]["score"] == 0.9


def test_decode_nms_keeps_different_classes_same_spot():
    """Per-class NMS: overlapping boxes of DIFFERENT classes both survive."""
    raw = _raw([(100, 80, 40, 20, 0, 0.9), (100, 80, 40, 20, 1, 0.8)])
    out = decode_predictions(raw, NAMES, 0.5, 1.0, (0, 0), (640, 640))
    assert sorted(d["label"] for d in out) == ["mouse", "pen"]


def test_nms_geometry():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=float)
    scores = np.array([0.9, 0.8, 0.7])
    assert nms(boxes, scores, 0.45) == [0, 2]


def test_letterbox_shapes_and_gain():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    img, gain, pad = letterbox(frame, 640)
    assert img.shape == (640, 640, 3)
    assert abs(gain - 0.5) < 1e-6
    assert pad == (0, 140)
    # The padding rows are gray (114), the content rows black.
    assert img[0, 0, 0] == 114 and img[320, 320, 0] == 0


def test_available_false_without_model(tmp_path):
    assert YoloOnnxDetector.available(tmp_path / "missing.onnx") is False


def test_factory_falls_back_to_mediapipe(monkeypatch, tmp_path):
    """VISION_BACKEND=yolo_onnx without a model file → mediapipe detector."""
    from backend.core.config import config
    from backend.modules.vision import detector as det
    monkeypatch.setattr(config, "VISION_BACKEND", "yolo_onnx")
    monkeypatch.setattr(config, "YOLO_ONNX_MODEL", tmp_path / "missing.onnx")
    monkeypatch.setattr(det, "_detector", None)
    try:
        assert isinstance(det.get_detector(), det.ObjectDetector)
    finally:
        monkeypatch.setattr(det, "_detector", None)


def test_factory_default_is_mediapipe(monkeypatch):
    from backend.core.config import config
    from backend.modules.vision import detector as det
    monkeypatch.setattr(config, "VISION_BACKEND", "mediapipe")
    monkeypatch.setattr(det, "_track_detector", None)
    try:
        assert isinstance(det.get_tracking_detector(), det.ObjectDetector)
    finally:
        monkeypatch.setattr(det, "_track_detector", None)
