"""DebouncedTrigger: the timing rules behind "raise your hand and she waves".

Fully testable without a camera, mediapipe, or a websocket — that is the
point of pulling it out of the perception handler.
"""
from backend.modules.vision.reactions import DebouncedTrigger


def test_a_single_frame_does_not_fire():
    """One misread frame must not trigger a reaction."""
    t = DebouncedTrigger(frames=3, cooldown_s=10)
    assert t.observe(True, now=0.0) is False
    assert t.observe(True, now=0.1) is False


def test_fires_on_the_nth_consecutive_frame():
    t = DebouncedTrigger(frames=3, cooldown_s=10)
    assert t.observe(True, now=0.0) is False
    assert t.observe(True, now=0.1) is False
    assert t.observe(True, now=0.2) is True


def test_a_gap_resets_the_streak():
    """The condition must hold CONSECUTIVELY, not just often."""
    t = DebouncedTrigger(frames=3, cooldown_s=10)
    t.observe(True, now=0.0)
    t.observe(True, now=0.1)
    assert t.observe(False, now=0.2) is False   # hand briefly not seen
    assert t.observe(True, now=0.3) is False    # streak restarts from 1
    assert t.observe(True, now=0.4) is False
    assert t.observe(True, now=0.5) is True


def test_does_not_refire_while_the_condition_is_still_held():
    """A hand kept in the air must not wave every single frame — only once
    the cooldown has actually elapsed, which is a separate, later test."""
    t = DebouncedTrigger(frames=1, cooldown_s=10)
    assert t.observe(True, now=0.0) is True
    for i in range(1, 10):                        # up to, not through, cooldown
        assert t.observe(True, now=float(i)) is False, f"refired at t={i}"


def test_fires_again_after_the_cooldown_elapses():
    t = DebouncedTrigger(frames=1, cooldown_s=10)
    assert t.observe(True, now=0.0) is True
    assert t.observe(True, now=9.9) is False
    assert t.observe(True, now=10.1) is True


def test_lowering_and_raising_again_refires_immediately_after_cooldown():
    """Put the hand down and raise it again — a fresh gesture, not a hold."""
    t = DebouncedTrigger(frames=2, cooldown_s=5)
    t.observe(True, now=0.0)
    assert t.observe(True, now=0.1) is True
    t.observe(False, now=1.0)                   # hand down
    t.observe(True, now=6.0)
    assert t.observe(True, now=6.1) is True      # cooldown has elapsed


def test_reset_drops_the_streak_but_not_the_cooldown():
    t = DebouncedTrigger(frames=3, cooldown_s=10)
    assert t.observe(True, now=0.0) is False
    t.reset()
    # Streak restarts from zero — three MORE consecutive frames needed.
    assert t.observe(True, now=0.1) is False
    assert t.observe(True, now=0.2) is False
    assert t.observe(True, now=0.3) is True


def test_frames_and_cooldown_are_sanitised():
    """A caller passing 0 or a negative frame count must not fire on nothing."""
    t = DebouncedTrigger(frames=0, cooldown_s=-5)
    assert t.frames_needed == 1
    assert t.observe(True, now=0.0) is True
