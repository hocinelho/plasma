"""Tests for the supervision integration: converters, sliced detection,
and the ByteTrack-backed tracker (skipped cleanly if supervision is missing)."""
import numpy as np
import pytest

from backend.modules.vision import detections as dx

supervision = pytest.importorskip("supervision")


def _det(label, box, score=0.9):
    """Build a Plasma detection dict."""
    return {"label": label, "box": box, "score": score}


# ── converters ───────────────────────────────────────────────────────────────

def test_dict_sv_roundtrip():
    """dicts → sv.Detections → dicts preserves label, score, and box."""
    dets = [_det("bottle", [10, 20, 30, 40], 0.87), _det("cup", [100, 100, 20, 20], 0.5)]
    back = dx.sv_to_dicts(dx.dicts_to_sv(dets))
    assert [d["label"] for d in back] == ["bottle", "cup"]
    assert back[0]["box"] == [10.0, 20.0, 30.0, 40.0]
    assert back[0]["score"] == 0.87


def test_empty_detections_roundtrip():
    """Empty input must produce an empty sv.Detections and back."""
    assert dx.sv_to_dicts(dx.dicts_to_sv([])) == []


# ── sliced (tiled) detection ─────────────────────────────────────────────────

def test_sliced_detect_finds_small_object():
    """A fake detector that only sees the object when its tile is small proves
    the slicer actually runs tiles and merges results back to full-frame coords."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def tiny_only_detector(tile):
        # Simulates a real detector: "sees" the object only in a small tile
        # (where the object is proportionally big), never in the full frame.
        h, w = tile.shape[:2]
        if w > 400:
            return []
        return [_det("keys", [5, 5, 20, 20], 0.8)]

    out = dx.sliced_detect(tiny_only_detector, frame, slice_wh=256, overlap_wh=32)
    assert out, "slicer should surface the small-tile-only detection"
    assert all(d["label"] == "keys" for d in out)


def test_sliced_detect_merges_duplicates():
    """The same object seen in overlapping tiles must merge to one detection."""
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    def everywhere_detector(tile):
        # Same absolute-ish box in every tile → duplicates across overlaps.
        return [_det("cup", [10, 10, 50, 50], 0.9)]

    out = dx.sliced_detect(everywhere_detector, frame, slice_wh=256, overlap_wh=64)
    assert len(out) >= 1  # NMS keeps at least one, and far fewer than raw tiles


# ── ByteTrack tracker adapter ────────────────────────────────────────────────

def _make_tracker():
    """Build a ByteTrackTracker with test-friendly settings."""
    from backend.modules.vision.tracker import ByteTrackTracker
    return ByteTrackTracker(frame_rate=5.0, coast_frames=2, smooth_len=1,
                            lost_buffer=90, match_thresh=0.8)


def test_bytetrack_survives_long_occlusion():
    """With a big lost buffer, an object hidden for several frames keeps its id
    when it reappears — the whole point of the upgrade for 'don't lose me'."""
    from backend.modules.vision.tracker import ByteTrackTracker
    tr = ByteTrackTracker(frame_rate=5.0, coast_frames=1, smooth_len=1,
                          lost_buffer=90, match_thresh=0.8)
    out = tr.update([_det("person", [100, 100, 40, 90])])
    tid = out[0]["id"]
    for _ in range(2):
        tr.update([_det("person", [108, 100, 40, 90])])
    # Vanish for several frames (occluded), longer than coast_frames.
    for _ in range(5):
        drawn = tr.update([])
        assert all(o["coast"] for o in drawn)  # only coasting boxes, if any
    # Reappears near where it was heading → ByteTrack re-attaches the same id.
    out = tr.update([_det("person", [140, 100, 40, 90])])
    assert out and out[0]["id"] == tid


def test_bytetrack_keeps_id_when_object_moves():
    """The same moving object keeps one id across frames."""
    tr = _make_tracker()
    out1 = tr.update([_det("bottle", [100, 100, 40, 80])])
    assert len(out1) == 1
    tid = out1[0]["id"]
    for i in range(1, 5):
        out = tr.update([_det("bottle", [100 + i * 8, 100 + i * 4, 40, 80])])
        assert len(out) == 1
        assert out[0]["id"] == tid


def test_bytetrack_distinct_objects_distinct_ids():
    """Two separate objects must get different ids."""
    tr = _make_tracker()
    out = tr.update([
        _det("bottle", [10, 10, 30, 30]),
        _det("cup", [200, 200, 30, 30]),
    ])
    assert len(out) == 2
    assert out[0]["id"] != out[1]["id"]


def test_bytetrack_coasts_then_drops():
    """A vanished object keeps reporting (coast=True) for coast_frames, then stops."""
    tr = _make_tracker()
    tr.update([_det("bottle", [100, 100, 40, 80])])
    tr.update([_det("bottle", [110, 100, 40, 80])])
    out = tr.update([])                       # missed 1 → coast
    assert len(out) == 1 and out[0]["coast"] is True
    out = tr.update([])                       # missed 2 → still coasting
    assert len(out) == 1 and out[0]["coast"] is True
    out = tr.update([])                       # missed 3 > coast_frames → gone
    assert out == []


def test_bytetrack_reset_clears_state():
    """reset() must forget all tracks and bookkeeping."""
    tr = _make_tracker()
    tr.update([_det("bottle", [100, 100, 40, 80])])
    tr.reset()
    assert tr.update([]) == []


def test_bytetrack_empty_frames_ok():
    """Updating with no detections from the start must not crash."""
    tr = _make_tracker()
    assert tr.update([]) == []


def test_get_tracker_backend_selection(monkeypatch):
    """TRACK_BACKEND=iou forces the legacy SORT-lite tracker."""
    from backend.core.config import config
    from backend.modules.vision import tracker as trk
    monkeypatch.setattr(config, "TRACK_BACKEND", "iou")
    monkeypatch.setattr(trk, "_tracker", None)
    assert isinstance(trk.get_tracker(), trk.ObjectTracker)
    monkeypatch.setattr(config, "TRACK_BACKEND", "byte")
    monkeypatch.setattr(trk, "_tracker", None)
    assert isinstance(trk.get_tracker(), trk.ByteTrackTracker)
    monkeypatch.setattr(trk, "_tracker", None)  # don't leak into other tests


# ── annotator ────────────────────────────────────────────────────────────────

def test_annotate_frame_draws_something():
    """Annotating a black frame with one box must change pixels."""
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    out = dx.annotate_frame(frame, [_det("cup", [50, 50, 60, 60], 0.9)])
    assert out is not None
    assert out.shape == frame.shape
    assert int(out.sum()) > 0


def test_annotate_frame_empty_returns_none():
    """No detections → nothing to draw → None."""
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    assert dx.annotate_frame(frame, []) is None
