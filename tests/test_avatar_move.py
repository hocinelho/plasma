"""Tests for the avatar_move skill (voice-commanded avatar gestures)."""
from __future__ import annotations

import re
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


@pytest.mark.parametrize("utterance,clip", [
    ("can you walk", "walking"),
    ("lauf mal", "walking"),
    ("jump", "jump"),
    ("spring mal", "jump"),
    ("tell me a secret", "secret"),
    ("yell at me", "yelling"),
])
def test_full_body_clips_are_requested(utterance, clip):
    avatar_move.run({"utterance": utterance})
    assert avatar_state.pop_animation() == clip
    # Full-body clips shouldn't also fire an arm gesture.
    assert avatar_state.pop_gesture() is None


@pytest.mark.parametrize("utterance", ["can you dance for me", "do a backflip"])
def test_motions_without_a_clip_are_declined_honestly(utterance):
    """No clip for it — say so, don't fake it with an unrelated hand wave."""
    reply = avatar_move.run({"utterance": utterance})
    assert reply == avatar_move._UNSUPPORTED_REPLY[0]
    assert avatar_state.pop_animation() is None
    assert avatar_move.pop_last_gesture() is None


@pytest.mark.parametrize("utterance", [
    "Work. Work for me.",      # Whisper heard "Walk. Walk for me."
    "work walk",
])
def test_misheard_walk_still_walks(utterance):
    """Whisper reliably hears 'walk' as 'work'; the imperative forms recover it."""
    avatar_move.run({"utterance": utterance})
    assert avatar_state.pop_animation() == "walking"


@pytest.mark.parametrize("utterance", [
    "does this work", "does the camera work", "work on my code",
    "is my network working", "how does that work",
])
def test_genuine_work_questions_are_not_hijacked(utterance):
    """The 'work'→walk recovery must not swallow real questions about working."""
    assert avatar_move._pick_animation(utterance.lower()) is None


def test_german_thumbs_down_not_mistaken_for_running():
    """'daumen runter' contains 'run' — must not trip the unsupported list."""
    reply = avatar_move.run({"utterance": "daumen runter", "language": "de"})
    assert reply == avatar_move.GESTURES["thumbdown"][1]
    assert avatar_move.pop_last_gesture() == "thumbdown"


def test_every_animation_has_a_file_on_disk():
    """A clip name with no .fbx behind it would 404 in the browser."""
    anim_dir = Path(__file__).resolve().parents[1] / "frontend" / "animations"
    for name in avatar_move.ANIMATIONS:
        assert (anim_dir / f"{name}.fbx").is_file(), f"missing clip: {name}.fbx"


def test_animation_names_are_url_safe():
    """avatar.js builds /animations/<name>.fbx and rejects anything odd."""
    for name in avatar_state.known_animations():
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", name), name


def test_clips_are_discovered_from_disk(tmp_path, monkeypatch):
    """Dropping an .fbx in the folder must be enough to make it playable."""
    monkeypatch.setattr(avatar_state, "ANIMATIONS_DIR", tmp_path)
    (tmp_path / "moonwalk.fbx").write_bytes(b"x")
    (tmp_path / "idle-breathe.fbx").write_bytes(b"x")
    found = avatar_state.discover_animations(force=True)
    assert "moonwalk" in found and "idle-breathe" in found
    assert avatar_state.request_animation("moonwalk") is True


def test_unsafe_filenames_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_state, "ANIMATIONS_DIR", tmp_path)
    (tmp_path / "Weird Name!.fbx").write_bytes(b"x")
    (tmp_path / "-leading.fbx").write_bytes(b"x")
    assert avatar_state.discover_animations(force=True) == frozenset()


def test_idle_pool_is_the_idle_prefixed_clips(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_state, "ANIMATIONS_DIR", tmp_path)
    for n in ("idle-breathe", "idle-look", "walking"):
        (tmp_path / f"{n}.fbx").write_bytes(b"x")
    avatar_state.discover_animations(force=True)
    assert avatar_state.idle_animations() == ["idle-breathe", "idle-look"]


def test_missing_folder_falls_back_to_the_shipped_clips(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_state, "ANIMATIONS_DIR", tmp_path / "gone")
    avatar_state.discover_animations(force=True)
    assert "walking" in avatar_state.known_animations()


def test_longest_phrase_wins_across_gestures_and_animations():
    """One rule for both kinds of movement, so neither silently pre-empts.

    'shake your head' (15) beats the 'hop' inside 'hope' etc., and a bare
    'walk' still reaches the full-body clip.
    """
    avatar_move.run({"utterance": "shake your head"})
    assert avatar_move.pop_last_gesture() == "no"
    assert avatar_state.pop_animation() is None

    avatar_move.run({"utterance": "walk"})
    assert avatar_state.pop_animation() == "walking"
    assert avatar_move.pop_last_gesture() is None


def test_animations_map_to_known_names():
    for name in avatar_move.ANIMATIONS:
        assert name in avatar_state.known_animations()


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
