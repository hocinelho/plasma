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
    ("dance for me", "dance-samba"),
    ("tanz mal", "dance-samba"),
    ("do a backflip", "backflip"),
    ("run", "running"),
    ("sprint", "sprint"),
    ("turn left", "turn-left"),
    ("turn right", "turn-right"),
    ("walk back", "walk-back"),
    ("gangnam style", "dance-gangnam"),
    ("can you walk", "walking"),
    ("lauf mal", "walking"),
    ("jump", "jump"),
    ("spring mal", "jump"),
    ("yell at me", "yelling"),
])
def test_full_body_clips_are_requested(utterance, clip):
    avatar_move.run({"utterance": utterance})
    assert avatar_state.pop_animation() == clip
    # Full-body clips shouldn't also fire an arm gesture.
    assert avatar_state.pop_gesture() is None


@pytest.mark.parametrize("utterance", ["sit down please", "do a cartwheel"])
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


class TestTurning:
    """"Plasma, can you turn?" reached the LLM and she talked about turning
    instead of turning. Neither the trigger list nor the keyword table had a
    bare "turn" in it — only "turn left" and "turn right"."""

    def test_a_bare_turn_moves_her(self):
        avatar_move.run({"utterance": "Plasma. Can you turn? Turn.", "language": "en"})
        assert avatar_state.pop_animation() == "turn-left"

    def test_turn_is_a_trigger_so_it_reaches_the_skill_at_all(self):
        """The keyword table is only consulted once the router has picked
        this skill, and the trigger list is what decides that."""
        triggers = [t.lower() for t in avatar_move.META["triggers"]]
        assert "turn" in triggers

    def test_left_and_right_still_win_over_the_bare_word(self):
        """Longest matching phrase wins — "turn left" is longer than "turn"."""
        avatar_move.run({"utterance": "turn right", "language": "en"})
        assert avatar_state.pop_animation() == "turn-right"
        avatar_state.clear()
        avatar_move.run({"utterance": "turn left", "language": "en"})
        assert avatar_state.pop_animation() == "turn-left"

    def test_turning_around_plays_two_quarter_turns(self):
        """There is no 180° clip on disk, so facing away is a sequence —
        the same routine mechanism "show me everything you can do" uses."""
        avatar_move.run({"utterance": "turn around", "language": "en"})
        assert avatar_state.pop_routine() == ["turn-left", "turn-left"]
        assert avatar_state.pop_animation() is None

    def test_asking_to_see_her_back_is_the_same_request(self):
        """How it was actually said out loud, word for word."""
        avatar_move.run({"utterance": "I need to see your back.", "language": "en"})
        assert avatar_state.pop_routine() == ["turn-left", "turn-left"]

    def test_it_works_in_german(self):
        avatar_move.run({"utterance": "dreh dich um", "language": "de"})
        assert avatar_state.pop_routine() == ["turn-left", "turn-left"]

    def test_every_clip_it_names_exists_on_disk(self):
        """request_animation and request_routine both silently drop names
        they cannot find, so a typo here is a move that never happens and
        never complains."""
        known = avatar_state.known_animations()
        assert set(avatar_move.TURN_AROUND) <= known
        for clip in avatar_move.ANIMATION_KEYWORDS:
            assert clip in known, clip


class TestFacingYouAgain:
    """Turning is cumulative, so without a way to say "stop being turned"
    the only route back from a half-turn is guessing how many more turns
    make a full circle."""

    def test_face_me_comes_back_round(self):
        avatar_move.run({"utterance": "face me", "language": "en"})
        assert avatar_state.pop_gesture() == "face-front"

    def test_turn_back_to_me_is_not_another_turn_away(self):
        """It contains "turn", so it has to be checked before the turn
        keywords or it turns her further away — the opposite of the ask."""
        avatar_move.run({"utterance": "turn back to me", "language": "en"})
        assert avatar_state.pop_gesture() == "face-front"
        assert avatar_state.pop_animation() is None

    def test_it_works_in_german(self):
        avatar_move.run({"utterance": "schau mich an", "language": "de"})
        assert avatar_state.pop_gesture() == "face-front"

    def test_looking_at_the_camera_is_still_the_vision_skill(self):
        """"Look at the camera" means "use your eyes", not "rotate" — and it
        is one of the vision skill's triggers."""
        assert not any("look at the camera" in p
                       for p in avatar_move.FACE_FRONT_KEYWORDS)

    def test_the_marker_is_a_gesture_the_shared_store_accepts(self):
        """request_gesture silently rejects names outside KNOWN_GESTURES, so
        this would have been a reply with no movement behind it."""
        assert "face-front" in avatar_state.KNOWN_GESTURES
