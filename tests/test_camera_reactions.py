"""Tests for the "she reacts to the camera" wiring on the frontend.

Server-side behaviour (raise a hand → she waves + says hello, debounced and
cooled down) is verified end to end in tests/test_perception_ws_reactions.py.
What is pinned here is the browser half: the alert message carries the
reaction through to the avatar, and vision can actually be turned on from a
stage/overlay page where its normal toggle button is hidden by CSS.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


class TestAlertCarriesAGesture:
    def test_a_gesture_on_an_alert_is_played(self):
        block = INDEX.split("if (msg.type === 'alert')", 1)[1][:700]
        assert "msg.gesture" in block
        assert "window.avatarGesture(msg.gesture)" in block

    def test_a_reaction_does_not_interrupt_a_live_conversation(self):
        """The same guard the alert audio already uses — a stray hand-raise
        must not barge into an answer that is already being given."""
        block = INDEX.split("if (msg.type === 'alert')", 1)[1][:700]
        assert "msg.gesture && !isBusy && !isRecording" in block


class TestWatchParam:
    def test_watch_turns_on_the_camera(self):
        assert "params.get('watch') === '1'" in INDEX
        block = INDEX.split("params.get('watch') === '1'", 1)[1][:300]
        assert "startVision()" in block

    def test_watch_is_off_by_default(self):
        """A plain ?stage=1 visit must not trigger a surprise camera prompt."""
        # The watch block must be reached only through its own condition —
        # i.e. it lives inside the `if (params.get('watch') === '1')` guard,
        # not unconditionally alongside the mic unlock.
        summon = INDEX.split("const summoned = overlay ||", 1)[1]
        watch_at = summon.index("params.get('watch') === '1'")
        guard_at = summon.rindex("if (", 0, watch_at)
        assert summon[guard_at:watch_at + 40].count("if (") == 1


class TestServerCanAlwaysReachHer:
    def test_docs_mention_camera_reactions(self):
        doc = (ROOT / "docs" / "phone-setup.md").read_text(encoding="utf-8")
        assert "watch=1" in doc or "Camera reactions" in doc
