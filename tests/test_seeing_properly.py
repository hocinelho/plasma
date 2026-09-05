"""When she looks, she should say what she sees.

"Fix the camera — we already have a tracking system and recognising
previously, she should be able to do that."

Right on both counts, and neither was missing. The object detector has been
in the project all along, powering "find my keys" and the tracking overlay.
Face recognition has been there too, and she greets people by name from the
perception socket. vision_query — the skill that answers "can you see me?" —
called neither. It ran MediaPipe, reported an expression, and stopped.

So the answer to "can you see me" was "you look neutral", from a system that
could have said who you were and what was on your desk. Not a missing
capability: an unused one.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.INFO)

from backend.skills import vision_query as vq  # noqa: E402

SRC = (ROOT / "backend" / "skills" / "vision_query.py").read_text(encoding="utf-8")


class _Detector:
    def __init__(self, found):
        self._found = found

    def detect(self, _frame):
        return self._found


@pytest.fixture
def detector(monkeypatch):
    """Swap in a scripted detector — no camera, no model download."""
    import backend.modules.vision.detector as det

    def use(found):
        monkeypatch.setattr(det, "get_detector", lambda: _Detector(found))
    return use


class TestObjectsInFrame:
    def test_it_names_what_it_sees(self, detector):
        detector([{"label": "cup", "score": 0.8}, {"label": "laptop", "score": 0.7}])
        assert vq._objects_in_frame(None, de=False) == ". I can also see cup and laptop"

    def test_one_object_reads_naturally(self, detector):
        detector([{"label": "cup", "score": 0.8}])
        assert vq._objects_in_frame(None, de=False) == ". I can also see cup"

    def test_it_does_not_tell_you_there_is_a_person(self, detector):
        """The question was "can you see ME". Answering "I can also see a
        person" is not news to the person asking."""
        detector([{"label": "person", "score": 0.99}])
        assert vq._objects_in_frame(None, de=False) == ""

    def test_furniture_is_scenery(self, detector):
        detector([{"label": "chair", "score": 0.9}, {"label": "dining table", "score": 0.9}])
        assert vq._objects_in_frame(None, de=False) == ""

    def test_low_confidence_guesses_are_dropped(self, detector):
        """One invented object undoes the credibility of a whole correct
        sentence, and the detector's low-confidence guesses are wild."""
        detector([{"label": "banana", "score": 0.2}, {"label": "cup", "score": 0.9}])
        assert "banana" not in vq._objects_in_frame(None, de=False)

    def test_duplicates_are_said_once(self, detector):
        detector([{"label": "cup", "score": 0.9}, {"label": "cup", "score": 0.8}])
        assert vq._objects_in_frame(None, de=False).count("cup") == 1

    def test_it_stops_before_it_becomes_a_list(self, detector):
        """Spoken aloud, an inventory is worse than a sentence."""
        detector([{"label": f"thing{i}", "score": 0.9} for i in range(10)])
        assert vq._objects_in_frame(None, de=False).count(",") <= vq._MAX_OBJECTS

    def test_nothing_in_frame_says_nothing(self, detector):
        detector([])
        assert vq._objects_in_frame(None, de=False) == ""

    def test_it_speaks_german_too(self, detector):
        detector([{"label": "cup", "score": 0.8}])
        assert "Ich sehe auch" in vq._objects_in_frame(None, de=True)

    def test_a_missing_detector_is_not_fatal(self):
        """Object detection is optional. Losing it should cost the extra
        sentence, not the answer."""
        assert vq._objects_in_frame(None, de=False) == ""


class TestSayingWhoYouAre:
    def test_recognition_is_no_longer_gated_on_the_wording(self):
        """It used to run only when the utterance contained "who" or
        "recognise", so "can you see me?" — the most obvious way to ask — got
        a bare expression read from a system that knew the name and did not
        say it."""
        block = SRC.split("Say WHO, not just what expression", 1)[1][:1200]
        assert "asked_outright" in block
        # identify() must be reached without depending on the wording
        ident = block.index("face_id.identify(frame)")
        gate = block.index("asked_outright")
        assert gate < ident or "if name:" in block

    def test_not_knowing_you_is_only_mentioned_when_asked(self):
        """Volunteering "I don't know you" at every glance is pestering —
        and she asks for a name on her own when she sees a stranger."""
        block = SRC.split("Say WHO, not just what expression", 1)[1][:1200]
        assert "elif asked_outright" in block

    def test_it_needs_recognition_to_actually_be_installed(self):
        """Without DeepFace, identify() returns None for everybody."""
        block = SRC.split("Say WHO, not just what expression", 1)[1][:1200]
        assert "face_id.is_available()" in block


class TestTheDetectorIsActuallyCalled:
    def test_the_answer_includes_both_halves(self):
        """Both are true and they answer different halves of the question, so
        the objects are appended to the expression read rather than replacing
        it."""
        assert "return summary + _objects_in_frame(frame, de)" in SRC

    def test_it_reuses_the_detector_the_rest_of_the_app_uses(self):
        """A second detector would be a second model load and a second set of
        answers to keep consistent."""
        assert "from backend.modules.vision.detector import get_detector" in SRC
