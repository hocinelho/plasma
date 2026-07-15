"""
MediaPipe-based object detector — Apache 2.0 license, no AGPL.

Model: EfficientDet-Lite0 (int8, ~4.4 MB), auto-downloaded on first use.
Input: BGR numpy array (from OpenCV or decoded JPEG bytes).
Output: list of {"label": str, "score": float, "box": [x, y, w, h]}

Lazy import: if mediapipe is not installed, raises a friendly ImportError
instead of crashing the whole app.
"""
from __future__ import annotations
import logging
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

log = logging.getLogger("plasma.vision.detector")

# Selectable model sizes (all Apache 2.0, auto-downloaded on first use).
# lite2 is noticeably more accurate than lite0 for ~3x the (still small) size.
_MODELS = {
    "efficientdet_lite0": (
        "https://storage.googleapis.com/mediapipe-models/"
        "object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite",
        "~4.4 MB",
    ),
    "efficientdet_lite2": (
        "https://storage.googleapis.com/mediapipe-models/"
        "object_detector/efficientdet_lite2/int8/1/efficientdet_lite2.tflite",
        "~12 MB",
    ),
}


def _model_path() -> Path:
    from backend.core.config import config
    name = config.VISION_DETECTOR_MODEL
    if name not in _MODELS:
        log.warning("Unknown VISION_DETECTOR_MODEL=%r — using efficientdet_lite0", name)
        name = "efficientdet_lite0"
    url, size = _MODELS[name]
    dest = config.VISION_MODEL_DIR / f"{name}.tflite"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading MediaPipe %s model (%s) → %s", name, size, dest)
        try:
            urllib.request.urlretrieve(url, dest)
            log.info("Model downloaded: %s", dest)
        except Exception as e:
            # Never brick detection because an OPT-IN bigger model can't be
            # fetched (offline / proxy / TLS). Fall back to lite0 if it's cached.
            dest.unlink(missing_ok=True)
            fallback = config.VISION_MODEL_DIR / "efficientdet_lite0.tflite"
            if name != "efficientdet_lite0" and fallback.exists():
                log.warning("Download of %s failed (%s) — using cached lite0", name, e)
                return fallback
            raise
    return dest


class ObjectDetector:
    """Lazy-loaded MediaPipe object detector (thread-safe after first load)."""

    def __init__(self, max_results: int = 10, score_threshold: float = 0.5):
        self._max_results = max_results
        self._score_threshold = score_threshold
        self._detector = None

    def _load(self) -> None:
        if self._detector is not None:
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
        except ImportError as e:
            raise ImportError(
                "mediapipe is not installed. "
                "Run: pip install mediapipe"
            ) from e

        model = _model_path()
        options = mp_vision.ObjectDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            max_results=self._max_results,
            score_threshold=self._score_threshold,
        )
        self._detector = mp_vision.ObjectDetector.create_from_options(options)
        log.info("MediaPipe ObjectDetector loaded (threshold=%.2f)", self._score_threshold)

    def detect(self, frame_bgr: np.ndarray) -> list[dict]:
        """
        Detect objects in a BGR frame (cv2 format).
        Returns list of {"label": str, "score": float, "box": [x, y, w, h]}.
        """
        self._load()
        import mediapipe as mp

        rgb = frame_bgr[:, :, ::-1].copy()  # BGR → RGB, contiguous
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)

        out = []
        for d in result.detections:
            if not d.categories:
                continue
            cat = d.categories[0]
            bb = d.bounding_box
            out.append({
                "label": cat.category_name,
                "score": round(float(cat.score), 3),
                "box": [bb.origin_x, bb.origin_y, bb.width, bb.height],
            })
        return out

    def detect_smart(self, frame_bgr: np.ndarray) -> list[dict]:
        """Detect with tiled (SAHI-style) inference when enabled, else plain.

        Tiling makes small objects (keys, remotes) visible to the model at the
        cost of a few extra inference passes — right for one-shot snapshots
        ("what do you see", "find my X"), wrong for the live tracking loop.
        """
        from backend.core.config import config
        if config.VISION_SLICING:
            try:
                from backend.modules.vision.detections import sliced_detect
                return sliced_detect(self.detect, frame_bgr)
            except Exception as e:
                log.warning("Sliced detection failed (%s) — plain detect", e)
        return self.detect(frame_bgr)


def _build_detector(max_results: int, score_threshold: float):
    """Detector factory honoring VISION_BACKEND, with mediapipe as the safe
    fallback (never-crash: a missing ONNX file or onnxruntime import failure
    must not break vision)."""
    from backend.core.config import config
    if config.VISION_BACKEND == "yolo_onnx":
        try:
            from backend.modules.vision.yolo_onnx import YoloOnnxDetector
            if YoloOnnxDetector.available():
                log.info("Detector backend: YOLO-ONNX (%s)", config.YOLO_ONNX_MODEL)
                return YoloOnnxDetector(
                    max_results=max_results, score_threshold=score_threshold,
                )
            log.warning(
                "VISION_BACKEND=yolo_onnx but %s is missing (or onnxruntime "
                "isn't installed) — falling back to mediapipe. See "
                "docs/yoloe-setup.md.", config.YOLO_ONNX_MODEL,
            )
        except Exception as e:
            log.warning("YOLO-ONNX backend failed (%s) — using mediapipe", e)
    return ObjectDetector(max_results=max_results, score_threshold=score_threshold)


# Module-level singleton — shared across skill + monitor
_detector = None


def get_detector(score_threshold: float | None = None):
    global _detector
    if _detector is None:
        from backend.core.config import config
        _detector = _build_detector(
            max_results=10,
            score_threshold=score_threshold or config.VISION_SCORE_THRESHOLD,
        )
    return _detector


# Separate instance for live tracking: a LOWER threshold + MORE results so the
# tracker sees many objects at once and doesn't lose them on a weak frame. Kept
# apart from the snapshot detector so the "what do you see" skill stays strict.
_track_detector = None


def get_tracking_detector():
    global _track_detector
    if _track_detector is None:
        from backend.core.config import config
        _track_detector = _build_detector(
            max_results=config.TRACK_MAX_OBJECTS,
            score_threshold=config.TRACK_CONF,
        )
    return _track_detector
