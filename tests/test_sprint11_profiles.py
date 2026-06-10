"""Tests for Sprint 11 — PA-65 speaker ID, PA-66 per-user memory, PA-67 voice selection."""
from __future__ import annotations
import pytest


# ── PA-65: enrollment phrase parsing ─────────────────────────────────────────

def test_parse_enroll_english():
    from backend.modules.voice.speaker_id import parse_enroll_command
    assert parse_enroll_command("remember my voice as Hocine") == "Hocine"
    assert parse_enroll_command("Remember my voice as hocine") == "Hocine"
    assert parse_enroll_command("enroll my voice as Sara") == "Sara"
    assert parse_enroll_command("register my voice Malik") == "Malik"
    assert parse_enroll_command("learn my voice as Tom.") == "Tom"


def test_parse_enroll_german():
    from backend.modules.voice.speaker_id import parse_enroll_command
    assert parse_enroll_command("merke dir meine stimme als Hocine") == "Hocine"
    assert parse_enroll_command("Merk dir meine Stimme als Anna") == "Anna"


def test_parse_enroll_negative():
    from backend.modules.voice.speaker_id import parse_enroll_command
    assert parse_enroll_command("remember that I like coffee") is None
    assert parse_enroll_command("what time is it") is None
    assert parse_enroll_command("") is None
    assert parse_enroll_command("remember my birthday is in June") is None


# ── PA-65: profile store ─────────────────────────────────────────────────────

def test_profiles_roundtrip(tmp_path, monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "PROFILES_PATH", tmp_path / "speakers.json")
    speaker_id._save_profiles({"Hocine": [0.1, 0.2, 0.3]})
    loaded = speaker_id._load_profiles()
    assert loaded == {"Hocine": [0.1, 0.2, 0.3]}
    assert speaker_id.list_speakers() == ["Hocine"]


def test_forget_speaker(tmp_path, monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "PROFILES_PATH", tmp_path / "speakers.json")
    speaker_id._save_profiles({"Anna": [1.0], "Tom": [0.5]})
    assert speaker_id.forget_speaker("anna") is True
    assert speaker_id.list_speakers() == ["Tom"]
    assert speaker_id.forget_speaker("nobody") is False


def test_load_profiles_missing_file(tmp_path, monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "PROFILES_PATH", tmp_path / "nope.json")
    assert speaker_id._load_profiles() == {}


# ── PA-65: cosine similarity ─────────────────────────────────────────────────

def test_cosine_identical():
    from backend.modules.voice.speaker_id import _cosine
    assert _cosine([1.0, 0.0, 0.5], [1.0, 0.0, 0.5]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    from backend.modules.voice.speaker_id import _cosine
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_vector():
    from backend.modules.voice.speaker_id import _cosine
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# ── PA-65: graceful degradation without resemblyzer ──────────────────────────

def test_identify_unavailable_returns_none(monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "is_available", lambda: False)
    assert speaker_id.identify(None) == (None, 0.0)


def test_enroll_unavailable_returns_message(monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "is_available", lambda: False)
    reply = speaker_id.enroll("Hocine", None)
    assert "resemblyzer" in reply


def test_identify_with_mocked_embedding(tmp_path, monkeypatch):
    """Full identify() path with a fake embedder — no resemblyzer needed."""
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "PROFILES_PATH", tmp_path / "speakers.json")
    monkeypatch.setattr(speaker_id, "is_available", lambda: True)
    monkeypatch.setattr(speaker_id, "_embed", lambda audio: [1.0, 0.0, 0.0])
    speaker_id._save_profiles({"Hocine": [1.0, 0.0, 0.0], "Anna": [0.0, 1.0, 0.0]})

    fake_audio = [0] * 16000  # len() works; > MIN_AUDIO_SECONDS * SAMPLE_RATE
    name, score = speaker_id.identify(fake_audio)
    assert name == "Hocine"
    assert score == pytest.approx(1.0)


def test_identify_below_threshold(tmp_path, monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "PROFILES_PATH", tmp_path / "speakers.json")
    monkeypatch.setattr(speaker_id, "is_available", lambda: True)
    # embedding far from any profile → cosine ~0 < threshold
    monkeypatch.setattr(speaker_id, "_embed", lambda audio: [0.0, 0.0, 1.0])
    speaker_id._save_profiles({"Hocine": [1.0, 0.0, 0.0]})

    name, score = speaker_id.identify([0] * 16000)
    assert name is None
    assert score < 0.5


# ── PA-66: per-user facts in MemoryStore ─────────────────────────────────────

def _tmp_store(tmp_path):
    from backend.modules.memory.store import MemoryStore
    return MemoryStore(db_path=tmp_path / "test.sqlite")


def test_facts_user_column(tmp_path):
    store = _tmp_store(tmp_path)
    store.add_fact("user_note", "likes coffee", user="Hocine")
    facts = store.get_facts(user="Hocine")
    assert len(facts) == 1
    assert facts[0]["user"] == "Hocine"


def test_facts_user_includes_shared(tmp_path):
    """user=<name> returns personal facts PLUS shared (NULL-user) facts."""
    store = _tmp_store(tmp_path)
    store.add_fact("user_note", "shared fact")              # global
    store.add_fact("user_note", "hocine fact", user="Hocine")
    store.add_fact("user_note", "anna fact", user="Anna")

    contents = {f["content"] for f in store.get_facts(user="Hocine")}
    assert contents == {"shared fact", "hocine fact"}


def test_facts_no_user_returns_all(tmp_path):
    store = _tmp_store(tmp_path)
    store.add_fact("user_note", "a", user="Hocine")
    store.add_fact("user_note", "b")
    assert len(store.get_facts()) == 2


def test_facts_user_and_category(tmp_path):
    store = _tmp_store(tmp_path)
    store.add_fact("preference", "dark mode", user="Hocine")
    store.add_fact("user_note", "note", user="Hocine")
    facts = store.get_facts(category="preference", user="Hocine")
    assert len(facts) == 1
    assert facts[0]["content"] == "dark mode"


# ── PA-66: per-user USER.md ──────────────────────────────────────────────────

def test_user_md_path_shared():
    from backend.modules.user.user_md import user_md_path, USER_MD_PATH
    assert user_md_path(None) == USER_MD_PATH


def test_user_md_path_named():
    from backend.modules.user.user_md import user_md_path
    p = user_md_path("hocine")
    assert p.name == "USER_Hocine.md"


def test_user_md_path_sanitized():
    from backend.modules.user.user_md import user_md_path
    p = user_md_path("h./..\\x")
    assert "/" not in p.name and "\\" not in p.name and ".." not in p.name


def test_remember_this_user_scoped(tmp_path, monkeypatch):
    import backend.skills.remember_this as rt
    monkeypatch.setattr(rt, "_memory", _tmp_store(tmp_path))
    reply = rt.run({"utterance": "remember that I like strong coffee", "speaker": "Hocine"})
    assert "Hocine" in reply
    facts = rt._memory.get_facts(category="user_note", user="Hocine")
    assert any("strong coffee" in f["content"] for f in facts)
    assert facts[0]["user"] == "Hocine"


# ── chat_service passes speaker into skills ──────────────────────────────────

def test_chat_service_passes_speaker(monkeypatch):
    captured = {}

    class _FakeSkill:
        name = "who_am_i"
        def invoke(self, args):
            captured.update(args)
            return "You're Hocine."

    class _FakeRegistry:
        def find_by_trigger(self, msg):
            return _FakeSkill()

    class _FakeMem:
        def add_message(self, *a, **kw): pass
        def get_facts(self, **kw): return []
        def mark_skill_used(self, *a, **kw): pass

    import backend.modules.router.chat_service as cs
    monkeypatch.setattr(cs, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(cs, "get_memory", lambda: _FakeMem())

    result = cs.handle_chat("s1", "who am i", language="en", speaker="Hocine")
    assert captured["speaker"] == "Hocine"
    assert result == "You're Hocine."


# ── PA-67: voice selection ───────────────────────────────────────────────────

def test_voice_select_switch(monkeypatch):
    from backend.skills import voice_select
    from backend.modules.voice import tts
    monkeypatch.setattr(tts, "list_available_voices",
                        lambda: ["de_DE-thorsten-medium.onnx", "en_US-ryan-high.onnx"])
    calls = {}
    monkeypatch.setattr(tts, "set_voice_override",
                        lambda p: calls.setdefault("path", p) or "de_DE-thorsten-medium")
    reply = voice_select.run({"utterance": "switch voice to thorsten"})
    assert "thorsten" in reply.lower()
    assert "thorsten" in str(calls["path"])


def test_voice_select_unknown_voice(monkeypatch):
    from backend.skills import voice_select
    from backend.modules.voice import tts
    monkeypatch.setattr(tts, "list_available_voices", lambda: ["en_US-ryan-high.onnx"])
    reply = voice_select.run({"utterance": "switch voice to bogus"})
    assert "ryan" in reply.lower()


def test_voice_select_list(monkeypatch):
    from backend.skills import voice_select
    from backend.modules.voice import tts
    monkeypatch.setattr(tts, "list_available_voices",
                        lambda: ["de_DE-thorsten-medium.onnx", "en_US-ryan-high.onnx"])
    monkeypatch.setattr(tts, "get_voice_override_name", lambda: None)
    reply = voice_select.run({"utterance": "list voices"})
    assert "thorsten" in reply and "ryan" in reply


def test_voice_select_reset(monkeypatch):
    from backend.skills import voice_select
    from backend.modules.voice import tts
    calls = {}
    monkeypatch.setattr(tts, "set_voice_override", lambda p: calls.setdefault("path", p))
    monkeypatch.setattr(tts, "list_available_voices", lambda: [])
    reply = voice_select.run({"utterance": "reset voice"})
    assert calls["path"] is None
    assert "default" in reply.lower()


def test_voice_select_no_voices(monkeypatch):
    from backend.skills import voice_select
    from backend.modules.voice import tts
    monkeypatch.setattr(tts, "list_available_voices", lambda: [])
    reply = voice_select.run({"utterance": "switch voice to thorsten"})
    assert "voices" in reply.lower()


def test_voice_select_self_test():
    from backend.skills.voice_select import self_test
    assert self_test()


def test_voice_select_short_name():
    from backend.skills.voice_select import _short_name
    assert _short_name("de_DE-thorsten-medium.onnx") == "thorsten"
    assert _short_name("en_US-ryan-high.onnx") == "ryan"


# ── who_am_i skill ───────────────────────────────────────────────────────────

def test_who_am_i_identified():
    from backend.skills.who_am_i import run
    assert "Hocine" in run({"speaker": "Hocine"})


def test_who_am_i_identified_german():
    from backend.skills.who_am_i import run
    r = run({"speaker": "Hocine", "language": "de"})
    assert "Hocine" in r and "Stimme" in r


def test_who_am_i_not_installed(monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "is_available", lambda: False)
    from backend.skills.who_am_i import run
    assert "resemblyzer" in run({})


def test_who_am_i_no_profiles(monkeypatch):
    from backend.modules.voice import speaker_id
    monkeypatch.setattr(speaker_id, "is_available", lambda: True)
    monkeypatch.setattr(speaker_id, "list_speakers", lambda: [])
    from backend.skills.who_am_i import run
    assert "remember my voice" in run({})


def test_who_am_i_self_test():
    from backend.skills.who_am_i import self_test
    assert self_test()


# ── config ───────────────────────────────────────────────────────────────────

def test_config_speaker_vars():
    from backend.core.config import config
    assert hasattr(config, "SPEAKER_ID_ENABLED")
    assert isinstance(config.SPEAKER_THRESHOLD, float)
    assert 0.0 < config.SPEAKER_THRESHOLD < 1.0
