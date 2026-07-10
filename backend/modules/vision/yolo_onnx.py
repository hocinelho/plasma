"""
YOLO-ONNX detector backend — open-vocabulary recognition on the live feed.

Runs an Ultralytics-exported ONNX detector (YOLOE / YOLO-World with YOUR class
list baked in at export time, or a plain YOLO) on the onnxruntime Plasma
already ships. This is what lets the live tracking boxes say "pen" instead of
forcing everything into the 80 COCO classes.

The model file is NEVER downloaded here (this machine may be offline): export
it once on a connected PC and copy it to `.plasma/models/yoloe.onnx` — see
docs/yoloe-setup.md. Class names are read from the ONNX metadata that
Ultralytics embeds (override with YOLO_ONNX_CLASSES). Opt-in via
VISION_BACKEND=yolo_onnx; any failure falls back to the MediaPipe detector.

Pure NumPy pre/post-processing (letterbox, decode, NMS) — unit-testable
without a model. Handles detection ([1, 4+nc, N]) and segmentation exports
([1, 4+nc+32, N] — mask coefficients ignored) in either axis order.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("plasma.vision.yolo_onnx")

PAD_COLOR = 114  # Ultralytics letterbox gray


# ── pure helpers (unit-tested) ────────────────────────────────────────────────

def parse_names(raw: str) -> list[str]:
    """Parse the Ultralytics `names` metadata: "{0: 'pen', 1: 'mouse'}" or a
    plain list "['pen', 'mouse']" → ordered list of class names."""
    if not raw:
        return []
    try:
        obj = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []
    if isinstance(obj, dict):
        return [str(obj[k]) for k in sorted(obj, key=int)]
    if isinstance(obj, (list, tuple)):
        return [str(v) for v in obj]
    return []


def nms(boxes_xyxy: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> list[int]:
    """Greedy non-max suppression; returns kept indices, best score first."""
    order = scores.argsort()[::-1]
    x1, y1, x2, y2 = boxes_xyxy.T
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        ix1 = np.maximum(x1[i], x1[rest])
        iy1 = np.maximum(y1[i], y1[rest])
        ix2 = np.minimum(x2[i], x2[rest])
        iy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, ix2 - ix1) * np.maximum(0.0, iy2 - iy1)
        iou = inter / np.maximum(areas[i] + areas[rest] - inter, 1e-9)
        order = rest[iou <= iou_threshold]
    return keep


def decode_predictions(
    raw: np.ndarray,
    names: list[str],
    score_threshold: float,
    gain: float,
    pad: tuple[float, float],
    orig_hw: tuple[int, int],
    max_results: int = 10,
    iou_threshold: float = 0.45,
) -> list[dict]:
    """Ultralytics raw output → Plasma detection dicts in original-frame pixels.

    Accepts [1, C, N] or [1, N, C] where C = 4 + len(names) (+32 for seg
    exports whose mask coefficients we ignore). Boxes are cx,cy,w,h in the
    letterboxed image; `gain`/`pad` undo the letterbox.
    """
    nc = len(names)
    if nc == 0:
        return []
    arr = np.asarray(raw)
    if arr.ndim == 3:
        arr = arr[0]
    # Orient to [C, N] using the known channel count (4+nc, optionally +32).
    if arr.shape[0] - 4 - nc not in (0, 32):
        if arr.shape[1] - 4 - nc in (0, 32):
            arr = arr.T
        else:
            log.warning("Unexpected output shape %s for %d classes", arr.shape, nc)
            return []

    cls_scores = arr[4:4 + nc, :]
    scores = cls_scores.max(axis=0)
    class_ids = cls_scores.argmax(axis=0)
    mask = scores >= score_threshold
    if not mask.any():
        return []
    cx, cy, w, h = arr[0:4, mask]
    scores, class_ids = scores[mask], class_ids[mask]

    # Letterboxed cxcywh → original-frame xyxy.
    x1 = (cx - w / 2 - pad[0]) / gain
    y1 = (cy - h / 2 - pad[1]) / gain
    x2 = (cx + w / 2 - pad[0]) / gain
    y2 = (cy + h / 2 - pad[1]) / gain
    oh, ow = orig_hw
    x1, y1 = np.clip(x1, 0, ow), np.clip(y1, 0, oh)
    x2, y2 = np.clip(x2, 0, ow), np.clip(y2, 0, oh)
    xyxy = np.stack([x1, y1, x2, y2], axis=1)

    # Per-class NMS via the class-offset trick (boxes of different classes
    # can't suppress each other).
    offset = class_ids.astype(np.float32)[:, None] * 10_000.0
    keep = nms(xyxy + offset, scores, iou_threshold)[:max_results]

    out: list[dict] = []
    for i in keep:
        bx1, by1, bx2, by2 = (float(v) for v in xyxy[i])
        out.append({
            "label": names[int(class_ids[i])],
            "score": round(float(scores[i]), 3),
            "box": [round(bx1, 1), round(by1, 1),
                    round(bx2 - bx1, 1), round(by2 - by1, 1)],
        })
    return out


def letterbox(frame_bgr: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    """Resize keeping aspect ratio and pad to size×size; return (img, gain, pad)."""
    import cv2
    h, w = frame_bgr.shape[:2]
    gain = min(size / h, size / w)
    nh, nw = round(h * gain), round(w * gain)
    resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    out = np.full((size, size, 3), PAD_COLOR, dtype=np.uint8)
    pad_w, pad_h = (size - nw) / 2, (size - nh) / 2
    top, left = int(round(pad_h - 0.1)), int(round(pad_w - 0.1))
    out[top:top + nh, left:left + nw] = resized
    return out, gain, (left, top)


# ── detector ──────────────────────────────────────────────────────────────────

class YoloOnnxDetector:
    """Lazy-loaded onnxruntime YOLO detector with the ObjectDetector interface."""

    def __init__(self, model_path: Optional[Path] = None,
                 max_results: int = 10, score_threshold: float = 0.5):
        from backend.core.config import config
        self._path = Path(model_path or config.YOLO_ONNX_MODEL)
        self._max_results = max_results
        self._score_threshold = score_threshold
        self._imgsz = int(config.YOLO_ONNX_IMGSZ)
        self._iou = float(config.YOLO_ONNX_IOU)
        self._session = None
        self._input_name = ""
        self._names: list[str] = []

    @staticmethod
    def available(model_path: Optional[Path] = None) -> bool:
        """True when the model file exists and onnxruntime is importable."""
        from backend.core.config import config
        path = Path(model_path or config.YOLO_ONNX_MODEL)
        if not path.exists():
            return False
        try:
            import onnxruntime  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort
        if not self._path.exists():
            raise FileNotFoundError(
                f"YOLO ONNX model not found: {self._path} — export it on a "
                "connected PC and copy it here (see docs/yoloe-setup.md)."
            )
        log.info("Loading YOLO ONNX model: %s", self._path)
        self._session = ort.InferenceSession(
            str(self._path), providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name

        from backend.core.config import config
        override = [c.strip() for c in config.YOLO_ONNX_CLASSES.split(",") if c.strip()]
        meta = self._session.get_modelmeta().custom_metadata_map or {}
        self._names = override or parse_names(meta.get("names", ""))
        if not self._names:
            raise RuntimeError(
                "No class names: the ONNX has no 'names' metadata and "
                "YOLO_ONNX_CLASSES is not set in .env."
            )
        # Respect the export's image size if recorded ("[640, 640]").
        try:
            imgsz = ast.literal_eval(meta.get("imgsz", ""))
            if isinstance(imgsz, (list, tuple)) and imgsz:
                self._imgsz = int(imgsz[0])
        except (ValueError, SyntaxError):
            pass
        log.info("YOLO ONNX ready: %d classes %s… imgsz=%d",
                 len(self._names), self._names[:5], self._imgsz)

    def detect(self, frame_bgr: np.ndarray) -> list[dict]:
        """Detect objects in a BGR frame; same dict shape as ObjectDetector."""
        self._load()
        img, gain, pad = letterbox(frame_bgr, self._imgsz)
        blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        raw = self._session.run(None, {self._input_name: blob})[0]
        return decode_predictions(
            raw, self._names, self._score_threshold, gain, pad,
            frame_bgr.shape[:2], self._max_results, self._iou,
        )

    def detect_smart(self, frame_bgr: np.ndarray) -> list[dict]:
        """Tiled detection on snapshots when VISION_SLICING=true, else plain."""
        from backend.core.config import config
        if config.VISION_SLICING:
            try:
                from backend.modules.vision.detections import sliced_detect
                return sliced_detect(self.detect, frame_bgr)
            except Exception as e:
                log.warning("Sliced detection failed (%s) — plain detect", e)
        return self.detect(frame_bgr)
