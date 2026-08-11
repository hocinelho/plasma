"""Tests for the avatar_move skill (voice-commanded avatar gestures)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules import avatar_state  # noqa: E402
from backend.skills import avatar_move  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_pending():
    """Never leak a queued gesture between tests."""
    avatar_state.clear()
    yield
    avatar_state.clear()


def test_gesture_survives_the_skill_registry_boundary():
    """Regression: the registry loads skills under a synthetic module name.

    A skill that kept the queued gesture in its own globals wrote it to a
    different module object than main.py imports, so the avatar never moved.
    Drive the skill exactly as production does and assert it arrives.
    """
    from backend.modules.skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry.load_all()
    skill = registry.find_by_trigger("wave at me")
    assert skill is not None and skill.name == "avatar_move"

    skill.invoke({"utterance": "wave at me", "language": "en"})

    # main.py reads the shared store — this is the assertion that used to fail.
    assert avatar_state.pop_gesture() == "handup"


def test_self_test_passes():
    assert avatar_move.self_test() is True


@pytest.mark.parametrize("utterance,expected", [
    ("can you wave at me", "handup"),
    ("say hi", "handup"),
    ("winke mal", "handup"),
    ("give me a thumbs up", "thumbup"),
    ("daumen hoch", "thumbup"),
    ("nod", "yes"),
    ("shake your head", "no"),
    ("shrug", "shrug"),
    ("point at it", "index"),
])
def test_keyword_maps_to_gesture(utterance, expected):
    avatar_move.run({"utterance": utterance})
    assert avatar_move.pop_last_gesture() == expected


def test_thumbs_down_not_swallowed_by_thumbs_up():
    """Longest-match: 'thumbs down' contains no 'thumbs up', but guard anyway."""
    avatar_move.run({"utterance": "give me a thumbs down"})
    assert avatar_move.pop_last_gesture() == "thumbdown"


def test_generic_request_still_moves():
    reply = avatar_move.run({"utterance": "do some movement"})
    assert avatar_move.pop_last_gesture() in avatar_move._SURPRISE
    # Must not borrow a gesture-specific line like "No idea!".
    assert reply in [en for en, _ in avatar_move._SURPRISE_REPLIES]


def test_german_replies():
    reply = avatar_move.run({"utterance": "winke mal", "language": "de"})
    assert reply == avatar_move.GESTURES["handup"][1]


def test_gesture_is_popped_only_once():
    avatar_move.run({"utterance": "wave"})
    assert avatar_move.pop_last_gesture() == "handup"
    assert avatar_move.pop_last_gesture() is None


def test_stale_gesture_is_not_returned():
    avatar_move.run({"utterance": "wave"})
    assert avatar_move.pop_last_gesture(max_age_s=-1) is None


def test_request_gesture_rejects_unknown_names():
    assert avatar_state.request_gesture("moonwalk") is False
    assert avatar_move.pop_last_gesture() is None


@pytest.mark.parametrize("utterance", [
    "can you walk", "jump", "can you dance for me", "lauf mal", "spring",
])
def test_whole_body_motion_is_declined_honestly(utterance):
    """No animation clips installed — say so, don't fake it with a hand wave."""
    reply = avatar_move.run({"utterance": utterance})
    assert reply == avatar_move._UNSUPPORTED_REPLY[0]
    assert avatar_move.pop_last_gesture() is None


def test_supported_gesture_still_wins_when_mentioned_alongside_walking():
    reply = avatar_move.run({"utterance": "instead of walking, just wave"})
    assert reply == avatar_move.GESTURES["handup"][0]
    assert avatar_move.pop_last_gesture() == "handup"


def test_every_known_gesture_is_playable_by_the_renderer():
    """Names must exist in the renderer, or playGesture silently does nothing."""
    for name in avatar_move.GESTURES:
        assert name in avatar_state.KNOWN_GESTURES


def test_replies_have_no_emoji_since_tts_speaks_them():
    """Piper reads the reply aloud, so it must stay plain text."""
    for english, german in avatar_move.GESTURES.values():
        for text in (english, german):
            assert all(ord(ch) < 0x2190 for ch in text), f"emoji in reply: {text!r}"


def test_every_reply_maps_to_a_known_gesture():
    for name in avatar_move.KEYWORDS:
        assert name in avatar_move.GESTURES
    for name in avatar_move._SURPRISE:
        assert name in avatar_move.GESTURES
