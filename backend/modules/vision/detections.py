"""
Supervision interop — converters and helpers around `sv.Detections`.

Plasma's vision pipeline speaks plain dicts ({"label", "score", "box"} with
box = [x, y, w, h] px). Roboflow Supervision (MIT) speaks `sv.Detections`
(xyxy NumPy arrays). This module converts between the two and wraps the
supervision tools Plasma uses:

  • sliced_detect() — SAHI-style tiled inference (sv.InferenceSlicer): the
    detector runs on overlapping tiles so SMALL objects (keys, remotes) stop
    being invisible; overlaps are merged with NMS.
  • annotate_frame() — draw labeled boxes on a frame (Box/LabelAnnotator)
    for debug snapshots and the UI.

supervision is lazy-imported everywhere (repo convention for heavy deps);
every caller degrades gracefully when it isn't installed.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np

log = logging.getLogger("plasma.vision.detections")

# Stable runtime mapping label -> int class id (supervision wants ints).
_LABEL_IDS: dict[str, int] = {}


def is_available() -> bool:
    """True when the supervision package is importable."""
    try:
        import supervision  # noqa: F401
        return True
    except Exception:
        return False


def _class_id(label: str) -> int:
    """Return a stable int id for a label, growing the map on first sight."""
    if label not in _LABEL_IDS:
        _LABEL_IDS[label] = len(_LABEL_IDS)
    return _LABEL_IDS[label]


def dicts_to_sv(dets: list[dict]):
    """Convert Plasma detection dicts to sv.Detections (labels kept in .data)."""
    import supervision as sv

    if not dets:
        return sv.Detections.empty()
    xyxy = np.array(
        [[d["box"][0], d["box"][1],
          d["box"][0] + d["box"][2], d["box"][1] + d["box"][3]] for d in dets],
        dtype=np.float32,
    )
    return sv.Detections(
        xyxy=xyxy,
        confidence=np.array([float(d.get("score", 0.0)) for d in dets], dtype=np.float32),
        class_id=np.array([_class_id(str(d.get("label", ""))) for d in dets], dtype=int),
        data={"label": np.array([str(d.get("label", "")) for d in dets])},
    )


def sv_to_dicts(detections) -> list[dict]:
    """Convert sv.Detections back to Plasma dicts ([x, y, w, h] boxes).

    Includes "id" when the detections carry tracker ids.
    """
    out: list[dict] = []
    labels = detections.data.get("label") if detections.data else None
    for i in range(len(detections)):
        x1, y1, x2, y2 = (float(v) for v in detections.xyxy[i])
        d = {
            "label": str(labels[i]) if labels is not None else "",
            "score": round(float(detections.confidence[i]), 3)
            if detections.confidence is not None else 0.0,
            "box": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
        }
        if detections.tracker_id is not None:
            d["id"] = int(detections.tracker_id[i])
        out.append(d)
    return out


def sliced_detect(
    detect_fn: Callable[[np.ndarray], list[dict]],
    frame_bgr: np.ndarray,
    slice_wh: int = 384,
    overlap_wh: int = 64,
) -> list[dict]:
    """Run a dict-based detector over overlapping tiles and merge with NMS.

    Small objects that are a handful of pixels in the full frame fill a whole
    tile, so the detector actually sees them. Falls back to a plain full-frame
    detect_fn() call if supervision isn't installed.
    """
    try:
        import supervision as sv
    except Exception:
        return detect_fn(frame_bgr)

    def _callback(tile: np.ndarray):
        return dicts_to_sv(detect_fn(tile))

    slicer = sv.InferenceSlicer(
        callback=_callback,
        slice_wh=slice_wh,
        overlap_wh=overlap_wh,
        iou_threshold=0.4,
    )
    merged = slicer(frame_bgr)
    log.info("sliced_detect: %d detections after tile merge", len(merged))
    return sv_to_dicts(merged)


def annotate_frame(frame_bgr: np.ndarray, dets: list[dict]) -> Optional[np.ndarray]:
    """Return a copy of the frame with labeled boxes drawn, or None if
    supervision is unavailable or there is nothing to draw."""
    if not dets:
        return None
    try:
        import supervision as sv
    except Exception:
        return None

    detections = dicts_to_sv(dets)
    labels = [f"{d['label']} {d['score']:.2f}" for d in dets]
    scene = frame_bgr.copy()
    scene = sv.BoxAnnotator().annotate(scene=scene, detections=detections)
    scene = sv.LabelAnnotator().annotate(scene=scene, detections=detections, labels=labels)
    return scene
