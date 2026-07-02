"""Tests for personal object memory (pure logic — no camera / MediaPipe)."""
import numpy as np
import pytest

from backend.modules.vision import object_memory as om


# ── command parsing ───────────────────────────────────────────────────────────

def test_parse_enroll_english():
    assert om.parse_enroll_command("remember this as my keys") == "keys"
    assert om.parse_enroll_command("save this as my wallet") == "wallet"
    assert om.parse_enroll_command("memorize this as the red mug") == "red mug"
    assert om.parse_enroll_command("this is my car key") == "car key"


def test_parse_enroll_german():
    assert om.parse_enroll_command("merke dir das als meine Brille") == "brille"
    assert om.parse_enroll_command("das ist mein Schlüssel") == "schlüssel"


def test_parse_enroll_rejects_face_and_noise():
    # Must not hijack face enrollment.
    assert om.parse_enroll_command("this is my face") is None
    assert om.parse_enroll_command("remember this as my face") is None
    assert om.parse_enroll_command("what time is it") is None
    assert om.parse_enroll_command("find my keys") is None


# ── cosine / crop (pure) ──────────────────────────────────────────────────────

def test_cosine_identical_and_orthogonal():
    a = np.array([1.0, 0.0, 0.0])
    assert om.cosine(a, a) == pytest.approx(1.0)
    assert om.cosine(a, np.array([0.0, 1.0, 0.0])) == pytest.approx(0.0)


def test_cosine_zero_vector_safe():
    assert om.cosine(np.zeros(3), np.ones(3)) == 0.0


def test_crop_box_and_center():
    frame = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)
    c = om.crop(frame, [10, 20, 30, 40])
    assert c.shape == (40, 30, 3)
    # None → centred square
    sq = om.crop(frame, None)
    assert sq.shape[0] == sq.shape[1] == 100


def test_crop_clamps_out_of_bounds():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    c = om.crop(frame, [40, 40, 100, 100])   # runs past the edge
    assert c.shape[0] > 0 and c.shape[1] > 0


# ── find_in_frame (embed mocked) ──────────────────────────────────────────────

def test_find_in_frame_picks_best_match(monkeypatch):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detections = [
        {"label": "cup", "score": 0.9, "box": [0, 0, 10, 10]},
        {"label": "bottle", "score": 0.8, "box": [50, 50, 10, 10]},
    ]
    # Enrolled reference embedding for "keys".
    ref = np.array([1.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(om, "_enrolled_embeddings", lambda name: [ref])

    # First candidate embeds close to ref, second orthogonal (by call order).
    seq = [np.array([0.99, 0.1], np.float32), np.array([0.0, 1.0], np.float32)]
    calls = {"i": 0}

    def embed_seq(region):
        e = seq[calls["i"] % len(seq)]
        calls["i"] += 1
        return e

    monkeypatch.setattr(om, "embed", embed_seq)
    monkeypatch.setattr(om.config, "OBJECT_MATCH_THRESHOLD", 0.55, raising=False)

    out = om.find_in_frame("keys", frame, detections)
    assert out is not None
    assert out["box"] == [0, 0, 10, 10]        # the close one
    assert out["score"] >= 0.55


def test_find_in_frame_none_when_below_threshold(monkeypatch):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detections = [{"label": "cup", "score": 0.9, "box": [0, 0, 10, 10]}]
    monkeypatch.setattr(om, "_enrolled_embeddings", lambda name: [np.array([1.0, 0.0], np.float32)])
    monkeypatch.setattr(om, "embed", lambda region: np.array([0.0, 1.0], np.float32))  # orthogonal
    monkeypatch.setattr(om.config, "OBJECT_MATCH_THRESHOLD", 0.55, raising=False)
    assert om.find_in_frame("keys", frame, detections) is None


def test_find_in_frame_none_when_not_enrolled(monkeypatch):
    monkeypatch.setattr(om, "_enrolled_embeddings", lambda name: [])
    out = om.find_in_frame("keys", np.zeros((10, 10, 3), np.uint8),
                           [{"label": "cup", "box": [0, 0, 5, 5]}])
    assert out is None


def test_remember_object_skill_self_test():
    from backend.skills import remember_object
    assert remember_object.self_test() is True
