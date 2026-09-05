"""Raising a hand at the camera should make her wave back.

It didn't, and the reason was a definition rather than a bug in the wiring:
"raised" meant "the wrist is in the upper half of the frame". Sitting at a
laptop, the camera fills the upper half with your face — waving beside your
head puts the wrist at roughly 0.6, so the greeting never fired. You had to
hold your hand up near the ceiling for it to count.

It now means what the words mean: the hand is held up, fingers above wrist,
wherever in the frame that happens.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.vision.perception import is_raised  # noqa: E402

_WRIST, _KNUCKLE = 0, 9


def hand(wrist_y: float, knuckle_y: float):
    """21 MediaPipe landmarks, with only the two this reads set meaningfully."""
    lms = [(0.5, 0.5) for _ in range(21)]
    lms[_WRIST] = (0.5, wrist_y)
    lms[_KNUCKLE] = (0.5, knuckle_y)
    return lms


class TestRaised:
    def test_a_hand_held_up_beside_your_head_counts(self):
        """The exact case that was broken. At a normal sitting distance the
        wrist lands around 0.6 — below the frame's midpoint, and the old
        rule rejected it."""
        assert is_raised(hand(wrist_y=0.60, knuckle_y=0.48)) is True

    def test_a_hand_high_in_the_frame_still_counts(self):
        assert is_raised(hand(wrist_y=0.35, knuckle_y=0.22)) is True

    def test_a_hand_low_in_the_frame_counts_if_it_is_held_up(self):
        """Standing far back, or a low camera: position in frame says nothing
        about whether you are holding your hand up."""
        assert is_raised(hand(wrist_y=0.92, knuckle_y=0.78)) is True

    def test_a_hand_resting_on_the_desk_does_not(self):
        """Palm down, knuckles level with the wrist — the commonest thing a
        hand does in front of a laptop, and it must not greet anyone."""
        assert is_raised(hand(wrist_y=0.80, knuckle_y=0.79)) is False

    def test_a_hand_hanging_down_does_not(self):
        assert is_raised(hand(wrist_y=0.40, knuckle_y=0.55)) is False

    def test_it_ignores_where_in_the_frame_the_hand_is(self):
        """The same gesture, at four heights, must read the same. This is the
        whole change: the old rule gave two different answers here."""
        for top in (0.05, 0.30, 0.55, 0.80):
            assert is_raised(hand(wrist_y=top + 0.12, knuckle_y=top)) is True

    def test_it_accepts_landmark_objects_as_well_as_tuples(self):
        """MediaPipe hands back objects with .x/.y; the tests use tuples."""
        class _P:
            def __init__(self, x, y):
                self.x, self.y = x, y

        lms = [_P(0.5, 0.5) for _ in range(21)]
        lms[_WRIST], lms[_KNUCKLE] = _P(0.5, 0.6), _P(0.5, 0.45)
        assert is_raised(lms) is True


class TestItIsWiredUp:
    def test_the_perceiver_reports_it(self):
        src = (Path(__file__).resolve().parents[1] / "backend" / "modules"
               / "vision" / "perception.py").read_text(encoding="utf-8")
        assert '"raised": is_raised(lms)' in src
        # The old rule must be gone, not merely bypassed.
        assert "wrist_y < 0.5" not in src

    def test_the_socket_still_waves_on_it(self):
        src = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(
            encoding="utf-8")
        assert 'h.get("raised")' in src
        assert 'gesture="handup"' in src
