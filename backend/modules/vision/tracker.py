"""
Real-time multi-object tracker — assigns PERSISTENT IDs to detections.

Plasma already *detects* objects per frame (MediaPipe EfficientDet, Apache 2.0,
see ``detector.py``). This module adds the missing *tracking* layer: it matches
detections frame-to-frame by IoU and hands each object a stable ``id`` that
survives as it moves, so Plasma can follow things on the live "Watch me" feed,
draw boxes, and say "the bottle (#3) moved left".

Why not Ultralytics YOLO + ByteTrack (as VLM-AutoYOLO uses)? Ultralytics is
AGPL-3.0; Plasma deliberately stays Apache/MIT (see ``detector.py``). A classic
SORT-style IoU tracker gives persistent IDs with **zero new dependencies and no
license entanglement**, runs in microseconds, and rides on the detector we
already ship. For higher accuracy / open-vocabulary boxes there is the separate
LocateAnything tier (``locate.py``).

Everything here is pure functions over plain dicts/boxes — no camera, no models,
fully unit-testable. Boxes are ``[x, y, w, h]`` in pixels (the detector's format).
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("plasma.vision.tracker")


# ── geometry (pure) ──────────────────────────────────────────────────────────

def iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-union of two [x, y, w, h] boxes. 0 if disjoint."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center(box: list[float]) -> tuple[float, float]:
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


# ── tracker ──────────────────────────────────────────────────────────────────

# Exponential-smoothing weight for the reported box (0..1): higher = snappier,
# lower = smoother but laggier. 0.5 glides nicely without feeling sluggish.
_SMOOTH = 0.5


class Track:
    """One tracked object: stable id, smoothed box, velocity, and bookkeeping."""

    __slots__ = ("id", "label", "box", "sbox", "score", "age", "hits",
                 "_cx", "_cy", "vx", "vy")

    def __init__(self, tid: int, label: str, box: list[float], score: float):
        self.id = tid
        self.label = label
        self.box = box                 # last raw detection box
        self.sbox = list(box)          # exponentially-smoothed box (for display)
        self.score = score
        self.age = 0                   # cycles since last seen (0 = seen now)
        self.hits = 1                  # total times matched
        self._cx, self._cy = _center(box)
        self.vx = 0.0                  # velocity (px/cycle) of the box origin
        self.vy = 0.0

    def update(self, box: list[float], score: float) -> None:
        cx, cy = _center(box)
        self.vx, self.vy = cx - self._cx, cy - self._cy
        self._cx, self._cy = cx, cy
        self.box = box
        # Smooth toward the new box so the drawn rectangle glides, not jumps.
        self.sbox = [s + (b - s) * _SMOOTH for s, b in zip(self.sbox, box)]
        self.score = score
        self.age = 0
        self.hits += 1

    def predicted_box(self) -> list[float]:
        """Smoothed box pushed forward by velocity*age — used while coasting
        (detection briefly missed this object) so the box keeps following it."""
        x, y, w, h = self.sbox
        return [x + self.vx * self.age, y + self.vy * self.age, w, h]

    def direction(self) -> Optional[str]:
        """Coarse motion label from the last velocity, or None if ~still."""
        if abs(self.vx) < 3 and abs(self.vy) < 3:
            return None
        if abs(self.vx) >= abs(self.vy):
            return "right" if self.vx > 0 else "left"
        return "down" if self.vy > 0 else "up"

    def as_dict(self, coast: bool = False) -> dict:
        box = self.predicted_box() if coast else self.sbox
        return {
            "id": self.id,
            "label": self.label,
            "box": [round(v, 1) for v in box],
            "score": round(self.score, 3),
            "direction": self.direction(),
            "coast": coast,
        }


class ObjectTracker:
    """SORT-lite: greedy IoU matching of detections to existing tracks."""

    def __init__(self, iou_threshold: float = 0.3, max_age: int = 8,
                 coast_frames: int = 3):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        # Keep reporting a track (via predicted box) for this many missed cycles
        # so a momentary detection gap doesn't blink the box out.
        self.coast_frames = coast_frames
        self._tracks: list[Track] = []
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(self, detections: list[dict]) -> list[dict]:
        """Advance one cycle.

        ``detections`` is the detector's output: ``[{"label", "score", "box"}]``.
        Returns the live tracks as dicts (``id``, ``label``, ``box``, ``direction``).
        """
        # Age every existing track by one cycle first.
        for tr in self._tracks:
            tr.age += 1

        unmatched = list(range(len(detections)))

        # Greedy best-IoU matching, label-aware (don't morph a cup into a person).
        # Build all candidate (iou, det_idx, track) triples, match highest first.
        candidates = []
        for di, det in enumerate(detections):
            for tr in self._tracks:
                if tr.label != det["label"]:
                    continue
                score = iou(tr.box, det["box"])
                if score >= self.iou_threshold:
                    candidates.append((score, di, tr))
        candidates.sort(key=lambda c: c[0], reverse=True)

        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for score, di, tr in candidates:
            if di in used_dets or id(tr) in used_tracks:
                continue
            det = detections[di]
            tr.update(det["box"], det["score"])
            used_tracks.add(id(tr))
            used_dets.add(di)

        # Spawn new tracks for unmatched detections.
        for di in unmatched:
            if di in used_dets:
                continue
            det = detections[di]
            self._tracks.append(Track(self._next_id, det["label"], det["box"], det["score"]))
            self._next_id += 1

        # Retire stale tracks.
        self._tracks = [tr for tr in self._tracks if tr.age <= self.max_age]

        # Report matched tracks AND recently-missed ones (coasting on their
        # predicted box) so boxes stay put and keep moving without blinking.
        out = []
        for tr in self._tracks:
            if tr.age == 0:
                out.append(tr.as_dict(coast=False))
            elif tr.age <= self.coast_frames:
                out.append(tr.as_dict(coast=True))
        return out

    @property
    def tracks(self) -> list[Track]:
        return self._tracks


# ── natural-language summary (pure) ──────────────────────────────────────────

def summarize_tracks(tracks: list[dict], de: bool = False) -> str:
    """One-line summary of what's being tracked, with counts and motion."""
    if not tracks:
        return "Ich sehe gerade keine Objekte." if de else "I don't see any objects right now."

    # Count by label.
    counts: dict[str, int] = {}
    for t in tracks:
        counts[t["label"]] = counts.get(t["label"], 0) + 1

    parts = []
    for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if de:
            parts.append(f"{n}× {label}" if n > 1 else label)
        else:
            parts.append(f"{n} {label}s" if n > 1 else f"a {label}")

    joined = ", ".join(parts)
    if de:
        return f"Ich verfolge: {joined}."
    return f"I'm tracking: {joined}."


# ── module-level singleton ───────────────────────────────────────────────────

_tracker: Optional[ObjectTracker] = None


def get_tracker() -> ObjectTracker:
    global _tracker
    if _tracker is None:
        from backend.core.config import config
        _tracker = ObjectTracker(
            iou_threshold=0.3,
            max_age=config.TRACK_MAX_AGE,
            coast_frames=config.TRACK_COAST_FRAMES,
        )
    return _tracker


def is_available() -> bool:
    """Tracking works whenever the (Apache-2.0) detector is importable."""
    from backend.core.config import config
    if not config.TRACK_ENABLED:
        return False
    try:
        import mediapipe  # noqa: F401
        return True
    except Exception:
        return False
