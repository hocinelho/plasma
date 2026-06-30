"""Tests for the pure-Python object tracker (no camera, no MediaPipe)."""
from backend.modules.vision.tracker import (
    iou,
    ObjectTracker,
    summarize_tracks,
)


def _det(label, box, score=0.9):
    return {"label": label, "box": box, "score": score}


# ── IoU geometry ─────────────────────────────────────────────────────────────

def test_iou_identical():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_iou_disjoint():
    assert iou([0, 0, 10, 10], [50, 50, 10, 10]) == 0.0


def test_iou_half_overlap():
    # Two 10x10 boxes overlapping in a 5x10 region → inter=50, union=150.
    assert abs(iou([0, 0, 10, 10], [5, 0, 10, 10]) - (50 / 150)) < 1e-6


# ── ID persistence ───────────────────────────────────────────────────────────

def test_track_keeps_id_when_object_moves():
    tr = ObjectTracker(iou_threshold=0.3, max_age=5)
    out1 = tr.update([_det("bottle", [100, 100, 40, 80])])
    assert len(out1) == 1
    first_id = out1[0]["id"]

    # Move slightly — boxes still overlap → same id.
    out2 = tr.update([_det("bottle", [108, 104, 40, 80])])
    assert out2[0]["id"] == first_id


def test_distinct_objects_get_distinct_ids():
    tr = ObjectTracker()
    out = tr.update([
        _det("bottle", [10, 10, 30, 30]),
        _det("cup", [200, 200, 30, 30]),
    ])
    ids = sorted(o["id"] for o in out)
    assert ids == [1, 2]


def test_label_change_does_not_reuse_track():
    tr = ObjectTracker(iou_threshold=0.3, coast_frames=0)
    a = tr.update([_det("cup", [10, 10, 30, 30])])
    # Same location but a different label → must be a new id, not morph the cup.
    # coast_frames=0 so the old cup isn't also reported as coasting.
    b = tr.update([_det("person", [10, 10, 30, 30])])
    assert len(b) == 1
    assert b[0]["label"] == "person"
    assert b[0]["id"] != a[0]["id"]


def test_track_retired_after_max_age():
    tr = ObjectTracker(iou_threshold=0.3, max_age=2)
    tr.update([_det("bottle", [0, 0, 20, 20])])
    # Object disappears for max_age+1 cycles.
    for _ in range(3):
        tr.update([])
    # Reappearing now should get a fresh id (old track retired).
    out = tr.update([_det("bottle", [0, 0, 20, 20])])
    assert out[0]["id"] == 2


def test_direction_reported_on_horizontal_move():
    tr = ObjectTracker(iou_threshold=0.1)
    tr.update([_det("ball", [0, 100, 20, 20])])
    # Move right but keep boxes overlapping so the track matches.
    out = tr.update([_det("ball", [10, 100, 20, 20])])
    assert out[0]["direction"] == "right"


# ── Coasting (no blink on a missed detection) ────────────────────────────────

def test_track_coasts_over_missed_detection():
    tr = ObjectTracker(iou_threshold=0.3, max_age=8, coast_frames=3)
    tr.update([_det("bottle", [0, 100, 20, 20])])
    out = tr.update([_det("bottle", [10, 100, 20, 20])])   # moving right
    moved_id = out[0]["id"]

    # Detection misses this cycle — the box must still be reported (coasting),
    # not blink out, and it should keep moving in the same direction.
    coasted = tr.update([])
    assert len(coasted) == 1
    assert coasted[0]["id"] == moved_id
    assert coasted[0]["coast"] is True
    assert coasted[0]["box"][0] > 10        # predicted further right


def test_track_stops_reporting_after_coast_window():
    tr = ObjectTracker(iou_threshold=0.3, max_age=8, coast_frames=2)
    tr.update([_det("cup", [0, 0, 20, 20])])
    # Miss more cycles than the coast window → no longer reported.
    tr.update([]); tr.update([])
    out = tr.update([])
    assert out == []


def test_multiple_objects_tracked_together():
    tr = ObjectTracker(iou_threshold=0.3)
    out = tr.update([
        _det("person", [0, 0, 50, 100]),
        _det("bottle", [200, 50, 20, 60]),
        _det("cup", [300, 80, 25, 40]),
    ])
    assert len(out) == 3
    assert {o["label"] for o in out} == {"person", "bottle", "cup"}


# ── summary text ─────────────────────────────────────────────────────────────

def test_summarize_empty():
    assert "don't see" in summarize_tracks([]).lower()
    assert "keine" in summarize_tracks([], de=True).lower()


def test_summarize_counts_plurals():
    tracks = [
        {"id": 1, "label": "bottle", "box": [0, 0, 1, 1], "direction": None},
        {"id": 2, "label": "bottle", "box": [0, 0, 1, 1], "direction": None},
        {"id": 3, "label": "person", "box": [0, 0, 1, 1], "direction": None},
    ]
    out = summarize_tracks(tracks)
    assert "2 bottles" in out
    assert "a person" in out
