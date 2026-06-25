"""Tests for face/hand perception logic (pure functions — no camera/MediaPipe)."""
from collections import namedtuple
from unittest.mock import patch, MagicMock

import pytest

from backend.modules.vision.perception import (
    _finger_states,
    count_fingers,
    classify_gesture,
    classify_expression,
    summarize,
)
from backend.modules.vision import face_id

Pt = namedtuple("Pt", "x y z")


def _build_hand(thumb, index, middle, ring, pinky, handedness="Right", wrist_y=0.9):
    """Build 21 synthetic landmarks with the requested fingers up/down.

    Up finger: tip above (smaller y) its PIP joint.
    Right-hand thumb extended: tip.x < ip.x.
    """
    lm = [Pt(0.5, 0.5, 0.0) for _ in range(21)]
    lm[0] = Pt(0.5, wrist_y, 0.0)  # wrist

    # Thumb: ip=3, tip=4
    if handedness.lower().startswith("r"):
        lm[3] = Pt(0.40, 0.6, 0.0)
        lm[4] = Pt(0.30 if thumb else 0.45, 0.6, 0.0)
    else:
        lm[3] = Pt(0.40, 0.6, 0.0)
        lm[4] = Pt(0.50 if thumb else 0.35, 0.6, 0.0)

    # Four fingers: (tip, pip) pairs
    pairs = [(8, 6, index), (12, 10, middle), (16, 14, ring), (20, 18, pinky)]
    for tip, pip, up in pairs:
        lm[pip] = Pt(0.5, 0.4, 0.0)
        lm[tip] = Pt(0.5, 0.2 if up else 0.5, 0.0)
    return lm


# ── Finger counting ──────────────────────────────────────────────────────────

def test_finger_states_open_palm():
    lm = _build_hand(1, 1, 1, 1, 1)
    assert _finger_states(lm, "Right") == [1, 1, 1, 1, 1]
    assert count_fingers(lm, "Right") == 5


def test_finger_states_fist():
    lm = _build_hand(0, 0, 0, 0, 0)
    assert count_fingers(lm, "Right") == 0


def test_count_two_fingers():
    lm = _build_hand(0, 1, 1, 0, 0)
    assert count_fingers(lm, "Right") == 2


def test_thumb_handedness_left():
    lm = _build_hand(1, 0, 0, 0, 0, handedness="Left")
    assert _finger_states(lm, "Left")[0] == 1


# ── Gesture classification ───────────────────────────────────────────────────

def test_gesture_victory():
    lm = _build_hand(0, 1, 1, 0, 0)
    assert classify_gesture(lm, "Right") == "victory"


def test_gesture_victory_ignores_thumb():
    # Peace sign with thumb sticking out should still read as victory.
    lm = _build_hand(1, 1, 1, 0, 0)
    assert classify_gesture(lm, "Right") == "victory"


def test_gesture_thumbs_up():
    lm = _build_hand(1, 0, 0, 0, 0)
    assert classify_gesture(lm, "Right") == "thumbs_up"


def test_gesture_open_palm():
    lm = _build_hand(1, 1, 1, 1, 1)
    assert classify_gesture(lm, "Right") == "open_palm"


def test_gesture_fist():
    lm = _build_hand(0, 0, 0, 0, 0)
    assert classify_gesture(lm, "Right") == "fist"


def test_gesture_pointing():
    lm = _build_hand(0, 1, 0, 0, 0)
    assert classify_gesture(lm, "Right") == "pointing"


# ── Expression classification ────────────────────────────────────────────────

def test_expression_happy():
    bs = {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.7}
    out = classify_expression(bs)
    assert out["expression"] == "happy"
    assert out["smiling"] is True


def test_expression_sleepy_yawn():
    out = classify_expression({"jawOpen": 0.8})
    assert out["expression"] == "sleepy"


def test_expression_sleepy_eyes_closed():
    out = classify_expression({"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.8})
    assert out["eyes_closed"] is True
    assert out["expression"] == "sleepy"


def test_expression_wink_left():
    out = classify_expression({"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.05})
    assert out["wink"] == "left"
    assert out["expression"] == "winking"


def test_expression_neutral():
    out = classify_expression({})
    assert out["expression"] == "neutral"


# ── Summary text ─────────────────────────────────────────────────────────────

def test_summarize_happy_and_victory():
    perception = {
        "faces": [{"expression": "happy", "wink": None}],
        "hands": [{"gesture": "victory", "finger_count": 2}],
    }
    out = summarize(perception, de=False)
    assert "happy" in out.lower()
    assert "victory" in out.lower()


def test_summarize_finger_count_singular():
    perception = {"faces": [], "hands": [{"gesture": None, "finger_count": 1}]}
    out = summarize(perception, de=False)
    assert "1 finger" in out and "fingers" not in out


def test_summarize_nobody():
    out = summarize({"faces": [], "hands": []}, de=False)
    assert "don't see" in out.lower()


def test_summarize_german():
    perception = {"faces": [{"expression": "sleepy", "wink": None}], "hands": []}
    out = summarize(perception, de=True)
    assert "müde" in out.lower()


# ── Face enrollment phrase parsing ───────────────────────────────────────────

def test_face_enroll_parse_en():
    assert face_id.parse_enroll_command("remember my face as Hocine") == "Hocine"
    assert face_id.parse_enroll_command("learn my face as anna") == "Anna"


def test_face_enroll_parse_de():
    assert face_id.parse_enroll_command("merke dir mein gesicht als Hocine") == "Hocine"


def test_face_enroll_parse_none():
    assert face_id.parse_enroll_command("how many fingers") is None


# ── Skill integration (mocked camera + perceiver) ────────────────────────────

def test_vision_query_self_test():
    from backend.skills import vision_query
    assert vision_query.self_test() is True


def test_vision_query_reports_gesture():
    from backend.skills import vision_query

    fake_frame = MagicMock()
    fake_perception = {
        "faces": [{"expression": "happy", "wink": None}],
        "hands": [{"gesture": "victory", "finger_count": 2}],
    }
    fake_perceiver = MagicMock()
    fake_perceiver.perceive.return_value = fake_perception

    with patch.object(vision_query, "_capture", return_value=fake_frame), \
         patch("backend.modules.vision.perception.get_perceiver", return_value=fake_perceiver):
        result = vision_query.run({"utterance": "what am i doing", "language": "en"})

    assert "victory" in result.lower()


def test_vision_query_enroll_path():
    from backend.skills import vision_query

    fake_frame = MagicMock()
    with patch.object(vision_query, "_capture", return_value=fake_frame), \
         patch("backend.modules.vision.face_id.enroll", return_value="Got it — I'll remember your face, Hocine.") as enroll_mock:
        result = vision_query.run({"utterance": "remember my face as Hocine", "language": "en"})

    enroll_mock.assert_called_once()
    assert "remember your face" in result.lower()
