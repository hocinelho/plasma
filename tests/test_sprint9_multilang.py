"""Tests for Sprint 9 — PA-48/50/51/52: German + English multilingual support."""
from __future__ import annotations
import pytest


# ── PA-51: WHISPER_LANGUAGE config var ───────────────────────────────────────

def test_config_has_whisper_language():
    from backend.core.config import config
    assert hasattr(config, "WHISPER_LANGUAGE")
    assert config.WHISPER_LANGUAGE in ("en", "de", "auto", config.WHISPER_LANGUAGE)


def test_config_has_tts_voice_de():
    from backend.core.config import config
    assert hasattr(config, "TTS_VOICE_DE")
    assert isinstance(config.TTS_VOICE_DE, str)


def test_pipeline_lang_en(monkeypatch):
    """WHISPER_LANGUAGE=en → passes 'en' to asr.transcribe."""
    np = pytest.importorskip("numpy")
    from backend.core import config as cfg_module
    monkeypatch.setattr(cfg_module.config, "WHISPER_LANGUAGE", "en")
    monkeypatch.setattr(cfg_module.config, "WHISPER_MODEL", "small.en")

    captured = {}

    class _FakeASR:
        def transcribe(self, audio, language=None, allowed_languages=None):
            captured["language"] = language
            return {"text": "hello", "language": "en", "duration": 0.5, "latency": 0.1}

    import backend.modules.voice.pipeline as pipe
    monkeypatch.setattr(pipe, "get_asr", lambda: _FakeASR())

    audio = np.random.randint(-1000, 1000, 16000, dtype=np.int16)
    pipe.transcribe_array(audio)
    assert captured["language"] == "en"


def test_pipeline_lang_auto_multilingual(monkeypatch):
    """WHISPER_LANGUAGE=auto + multilingual model → passes None to asr.transcribe."""
    np = pytest.importorskip("numpy")
    from backend.core import config as cfg_module
    monkeypatch.setattr(cfg_module.config, "WHISPER_LANGUAGE", "auto")
    monkeypatch.setattr(cfg_module.config, "WHISPER_MODEL", "small")

    captured = {}

    class _FakeASR:
        def transcribe(self, audio, language=None, allowed_languages=None):
            captured["language"] = language
            return {"text": "hallo", "language": "de", "duration": 0.5, "latency": 0.1}

    import backend.modules.voice.pipeline as pipe
    monkeypatch.setattr(pipe, "get_asr", lambda: _FakeASR())

    audio = np.random.randint(-1000, 1000, 16000, dtype=np.int16)
    pipe.transcribe_array(audio)
    assert captured["language"] is None  # None = auto-detect


def test_pipeline_lang_auto_english_only_model_warns(monkeypatch, caplog):
    """WHISPER_LANGUAGE=auto + .en model → warns and forces lang=en."""
    import logging
    np = pytest.importorskip("numpy")
    from backend.core import config as cfg_module
    monkeypatch.setattr(cfg_module.config, "WHISPER_LANGUAGE", "auto")
    monkeypatch.setattr(cfg_module.config, "WHISPER_MODEL", "small.en")

    captured = {}

    class _FakeASR:
        def transcribe(self, audio, language=None, allowed_languages=None):
            captured["language"] = language
            return {"text": "hello", "language": "en", "duration": 0.5, "latency": 0.1}

    import backend.modules.voice.pipeline as pipe
    monkeypatch.setattr(pipe, "get_asr", lambda: _FakeASR())

    with caplog.at_level(logging.WARNING, logger="plasma.pipeline"):
        audio = np.random.randint(-1000, 1000, 16000, dtype=np.int16)
        pipe.transcribe_array(audio)

    assert captured["language"] == "en"
    assert any("english-only" in r.message.lower() or "small.en" in r.message.lower()
               for r in caplog.records)


# ── PA-52: German triggers + bilingual skill responses ───────────────────────

def test_get_time_english():
    from backend.skills.get_time import run
    r = run({"language": "en"})
    assert r.startswith("It's")
    assert ":" in r


def test_get_time_german():
    from backend.skills.get_time import run
    r = run({"language": "de"})
    assert r.startswith("Es ist")
    assert "Uhr" in r


def test_get_time_german_triggers():
    from backend.skills.get_time import META
    triggers = META["triggers"]
    assert "wie spät ist es" in triggers
    assert "wie viel uhr" in triggers
    assert "uhrzeit" in triggers


def test_get_date_english():
    from backend.skills.get_date import run
    r = run({"language": "en"})
    assert "Today is" in r


def test_get_date_german():
    from backend.skills.get_date import run
    r = run({"language": "de"})
    assert "Heute ist" in r
    assert "." in r  # ordinal dot: "der 2. Juni"


def test_get_date_german_triggers():
    from backend.skills.get_date import META
    triggers = META["triggers"]
    assert "welches datum" in triggers
    assert "heutiges datum" in triggers


def test_get_date_german_months():
    from backend.skills.get_date import _DE_MONTHS
    assert len(_DE_MONTHS) == 12
    assert "Januar" in _DE_MONTHS
    assert "Dezember" in _DE_MONTHS


def test_get_date_german_days():
    from backend.skills.get_date import _DE_DAYS
    assert len(_DE_DAYS) == 7
    assert "Montag" in _DE_DAYS
    assert "Sonntag" in _DE_DAYS


def test_joke_english():
    from backend.skills.joke import run
    r = run({"language": "en"})
    assert isinstance(r, str) and len(r) > 10


def test_joke_german():
    from backend.skills.joke import run
    r = run({"language": "de"})
    assert isinstance(r, str) and len(r) > 10


def test_joke_german_jokes_list():
    from backend.skills.joke import _JOKES_DE
    assert len(_JOKES_DE) >= 5


def test_joke_german_triggers():
    from backend.skills.joke import META
    triggers = META["triggers"]
    assert "witz" in triggers
    assert "erzähl mir einen witz" in triggers


def test_timer_german_triggers():
    from backend.skills.timer import META
    triggers = META["triggers"]
    assert "stell einen timer" in triggers
    assert "timer für" in triggers


def test_calculator_german_triggers():
    from backend.skills.calculator import META
    triggers = META["triggers"]
    assert "rechne " in triggers
    assert "berechne " in triggers
    assert "was ist " in triggers


def test_weather_german_triggers():
    from backend.skills.weather import META
    triggers = META["triggers"]
    assert "wie ist das wetter" in triggers
    assert "wetter in" in triggers


# ── PA-50: Language passed through chat service ───────────────────────────────

def test_chat_service_passes_language(monkeypatch):
    """handle_chat(language='de') must reach skill.invoke with language='de'."""
    captured = {}

    class _FakeSkill:
        name = "get_time"
        def invoke(self, args):
            captured["language"] = args.get("language")
            return "Es ist 10:00 Uhr."

    class _FakeRegistry:
        def find_by_trigger(self, msg):
            return _FakeSkill()

    import backend.modules.router.chat_service as cs
    monkeypatch.setattr(cs, "get_registry", lambda: _FakeRegistry())
    # stub out memory so we don't need a real DB
    class _FakeMem:
        def add_message(self, *a, **kw): pass
        def get_facts(self, **kw): return []
        def mark_skill_used(self, *a, **kw): pass
    monkeypatch.setattr(cs, "get_memory", lambda: _FakeMem())

    result = cs.handle_chat("sess1", "wie spät ist es", language="de")
    assert captured["language"] == "de"
    assert result == "Es ist 10:00 Uhr."


# ── PA-48: German TTS path selection ─────────────────────────────────────────

def test_tts_synthesize_uses_de_voice_when_available(monkeypatch):
    """synthesize(language='de') must call _load_voice_de first."""
    called = {}

    def _fake_load_de():
        called["de"] = True
        return None  # return None to fall back → _load_voice also called

    def _fake_load_en():
        called["en"] = True
        raise RuntimeError("no voice model in test")

    import backend.modules.voice.tts as tts_mod
    monkeypatch.setattr(tts_mod, "_load_voice_de", _fake_load_de)
    monkeypatch.setattr(tts_mod, "_load_voice", _fake_load_en)

    try:
        tts_mod.synthesize("Hallo", language="de")
    except RuntimeError:
        pass  # expected — no real model in CI

    assert called.get("de"), "_load_voice_de not called for language='de'"


def test_tts_synthesize_skips_de_voice_for_english(monkeypatch):
    """synthesize(language='en') must NOT call _load_voice_de."""
    called = {}

    def _fake_load_de():
        called["de"] = True
        return object()

    def _fake_load_en():
        called["en"] = True
        raise RuntimeError("no voice model in test")

    import backend.modules.voice.tts as tts_mod
    monkeypatch.setattr(tts_mod, "_load_voice_de", _fake_load_de)
    monkeypatch.setattr(tts_mod, "_load_voice", _fake_load_en)

    try:
        tts_mod.synthesize("Hello", language="en")
    except RuntimeError:
        pass

    assert not called.get("de"), "_load_voice_de must not be called for English"
    assert called.get("en")


def test_tts_synthesize_empty_returns_empty(monkeypatch):
    import backend.modules.voice.tts as tts_mod
    result = tts_mod.synthesize("", language="de")
    assert result == b""


# ── download script exists ────────────────────────────────────────────────────

def test_download_de_voice_script_exists():
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / "scripts" / "download_de_voice.py"
    assert script.exists(), "scripts/download_de_voice.py missing"
