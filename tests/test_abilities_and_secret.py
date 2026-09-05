"""Tests for the 'what can you do' and 'tell me a secret' skills."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules import avatar_state  # noqa: E402
from backend.skills import show_abilities, tell_secret  # noqa: E402


@pytest.fixture(autouse=True)
def _clear():
    avatar_state.clear()
    yield
    avatar_state.clear()


# ── listing abilities ────────────────────────────────────────────────────
def test_self_tests_pass():
    assert show_abilities.self_test() is True
    assert tell_secret.self_test() is True


def test_lists_real_moves_by_friendly_name():
    reply = show_abilities.run({})
    assert "samba" in reply
    assert "backflip" in reply
    # Internal clip names must never be spoken aloud.
    assert "dance-samba" not in reply
    assert "walk-back" not in reply


def test_ambient_idle_clips_are_not_announced():
    """idle-* are background motion, not a move to offer."""
    assert "idle" not in show_abilities.run({}).lower()


def test_list_follows_the_folder(monkeypatch):
    """Clips are auto-discovered, so the answer can't go stale."""
    monkeypatch.setattr(avatar_state, "known_animations",
                        lambda: frozenset({"moonwalk", "idle-x"}))
    monkeypatch.setattr(show_abilities, "known_animations",
                        lambda: frozenset({"moonwalk", "idle-x"}))
    reply = show_abilities.run({})
    assert "moonwalk" in reply
    assert "idle-x" not in reply


def test_it_performs_every_move_not_just_one():
    """Asked to show what she can do, one example is not an answer."""
    show_abilities.run({})
    routine = avatar_state.pop_routine()
    assert routine is not None
    listed = {n for n in avatar_state.known_animations()
              if not n.startswith(avatar_state.IDLE_PREFIX)}
    assert set(routine) == listed
    assert len(routine) > 5


def test_the_routine_ends_on_the_showy_moves():
    show_abilities.run({})
    routine = avatar_state.pop_routine()
    assert routine[-1].startswith("dance")


def test_ambient_idle_clips_are_not_performed():
    show_abilities.run({})
    routine = avatar_state.pop_routine() or []
    assert not any(n.startswith(avatar_state.IDLE_PREFIX) for n in routine)


def test_routine_rejects_unknown_clips():
    assert avatar_state.request_routine(["not-a-clip", "walking"]) == ["walking"]
    assert avatar_state.pop_routine() == ["walking"]


def test_routine_is_popped_only_once():
    avatar_state.request_routine(["walking", "jump"])
    assert avatar_state.pop_routine() == ["walking", "jump"]
    assert avatar_state.pop_routine() is None


def test_german_listing():
    reply = show_abilities.run({"language": "de"})
    assert "Ganzkörper" in reply and "Samba" in reply


def test_hyphenated_clip_names_are_spoken_naturally(monkeypatch):
    monkeypatch.setattr(show_abilities, "known_animations",
                        lambda: frozenset({"some-new-move"}))
    assert "some new move" in show_abilities.run({})


# ── telling a secret ─────────────────────────────────────────────────────
def test_a_secret_is_actually_told_not_teased():
    """The old behaviour only promised a secret and never delivered one."""
    reply = tell_secret.run({})
    assert len(reply) > 40
    assert not reply.strip().endswith(("secret.", "Geheimnis."))


def test_it_whispers_while_telling():
    tell_secret.run({})
    assert avatar_state.pop_animation() == "secret"


def test_secrets_vary():
    seen = {tell_secret.run({}) for _ in range(25)}
    assert len(seen) > 3


def test_german_secrets():
    reply = tell_secret.run({"language": "de"})
    assert any(op in reply for op in tell_secret._OPENERS_DE)


def test_secrets_are_plain_text_for_tts():
    for text in tell_secret.SECRETS_EN + tell_secret.SECRETS_DE:
        assert all(ord(ch) < 0x2190 for ch in text), text
        assert len(text) > 20


def _fake_store(monkeypatch, facts):
    """Swap MemoryStore on the real module.

    monkeypatch.setattr restores it afterwards; replacing the whole module in
    sys.modules would leak a fake into every later test in the run.
    """
    import backend.modules.memory.store as store_mod

    class _Store:
        def get_facts(self, **kw):
            if isinstance(facts, Exception):
                raise facts
            return facts

    monkeypatch.setattr(store_mod, "MemoryStore", _Store)


def test_memory_secret_needs_enough_facts(monkeypatch):
    """With a nearly empty memory a 'secret' would just parrot the one fact."""
    _fake_store(monkeypatch, [{"content": "Likes coffee"}])
    assert tell_secret._memory_secret("Hocine", german=False) is None


def test_memory_secret_uses_a_stored_fact(monkeypatch):
    _fake_store(monkeypatch, [{"content": "Works at Vodafone"},
                              {"content": "Lives in Moers"},
                              {"content": "Likes strong coffee"}])
    secret = tell_secret._memory_secret("Hocine", german=False)
    assert secret is not None
    assert any(f in secret for f in
               ("Works at Vodafone", "Lives in Moers", "Likes strong coffee"))


def test_secret_survives_memory_being_unavailable(monkeypatch):
    _fake_store(monkeypatch, RuntimeError("db locked"))
    assert tell_secret._memory_secret("Hocine", german=False) is None
    # The skill as a whole must still answer.
    assert len(tell_secret.run({})) > 40
