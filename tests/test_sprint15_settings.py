"""
Sprint 15 tests — PA-64, PA-81.

Covers:
- settings_control skill: model switching, language switching, queries
- update_check skill: version comparison, network error handling
- GET /api/version endpoint
- Runtime config modification

All native-lib modules (numpy, whisper, tts, speaker_id, wake_monitor) are
stubbed so the suite runs without numpy / resemblyzer / faster-whisper.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub native-dependency modules before importing backend.main
# (same approach as tests/test_sprint12_analytics.py)
# ---------------------------------------------------------------------------
_STUBBED_VOICE_MODULES = [
    "backend.modules.voice",
    "backend.modules.voice.pipeline",
    "backend.modules.voice.asr",
    "backend.modules.voice.tts",
    "backend.modules.voice.speaker_id",
    "backend.modules.voice.wake_monitor",
]


def _install_stubs():
    np_mod = types.ModuleType("numpy")
    sys.modules.setdefault("numpy", np_mod)

    # Import the real backend packages so stubs don't clobber them.
    import backend  # noqa: F401
    import backend.modules  # noqa: F401
    import backend.modules.memory  # noqa: F401
    import backend.modules.router  # noqa: F401
    import backend.modules.skills  # noqa: F401
    import backend.modules.user  # noqa: F401
    import backend.core  # noqa: F401

    # Always swap in a disposable module object, even if a real one is already
    # cached (e.g. another test file imported it first) — mutating a real
    # module's functions in place would leak past this test since restoring
    # the sys.modules entry wouldn't undo the mutation.
    for name in _STUBBED_VOICE_MODULES:
        sys.modules[name] = types.ModuleType(name)

    pipeline_mod = sys.modules["backend.modules.voice.pipeline"]
    pipeline_mod.transcribe_audio_bytes = lambda data: {"text": "", "error": "stub"}
    pipeline_mod.get_asr = lambda: None
    pipeline_mod.reload_model = lambda model_name: None

    # tts stub
    tts_mod = sys.modules["backend.modules.voice.tts"]
    tts_mod.synthesize = lambda text, lang=None: b""
    tts_mod.health_check = lambda: {"enabled": True, "loaded": False, "error": "stub"}
    tts_mod._load_voice = lambda: None
    tts_mod.VOICES_DIR = Path("/nonexistent/voices")
    tts_mod._resolve_model = lambda p: Path(p)

    # speaker_id stub
    sid_mod = sys.modules["backend.modules.voice.speaker_id"]
    sid_mod.parse_enroll_command = lambda text: None
    sid_mod.enroll = lambda name, audio: "stub"
    sid_mod.identify = lambda audio: (None, 0.0)
    sid_mod.list_speakers = lambda: []
    sid_mod.is_available = lambda: False

    # wake_monitor stub
    wm_mod = sys.modules["backend.modules.voice.wake_monitor"]

    async def _async_noop(*a, **kw):
        pass

    wm_class = types.SimpleNamespace(
        start=_async_noop,
        stop=_async_noop,
        add_client=lambda ws: None,
        remove_client=lambda ws: None,
    )
    wm_mod.wake_monitor = wm_class


# None of these need the voice stubs — only backend.main (imported lazily in
# the `client` fixture below) pulls in the pipeline/asr chain.
from fastapi.testclient import TestClient  # noqa: E402
from backend.core.config import config  # noqa: E402
from backend.skills import settings_control  # noqa: E402
from backend.skills import update_check  # noqa: E402


@pytest.fixture
def client():
    """Stub the voice pipeline only for the duration of this test, then
    restore sys.modules in `finally` so it never leaks into other test files."""
    from tests.stub_cleanup import snapshot as _snapshot_modules, restore as _restore_modules
    voice_snapshot = _snapshot_modules(_STUBBED_VOICE_MODULES)
    _install_stubs()
    try:
        import backend.main as main_mod
        with TestClient(main_mod.app, raise_server_exceptions=True) as c:
            yield c
    finally:
        _restore_modules(voice_snapshot)


# ---------------------------------------------------------------------------
# PA-64: settings_control skill — model switching
# ---------------------------------------------------------------------------
class TestSettingsControlModel:
    def setup_method(self):
        """Reset config to defaults before each test."""
        config.WHISPER_MODEL = "small.en"
        config.WHISPER_LANGUAGE = "en"

    def test_switch_to_faster_model(self):
        result = settings_control.run({"utterance": "switch to faster model"})
        assert "tiny.en" in result
        assert config.WHISPER_MODEL == "tiny.en"
        assert "restart" in result.lower()

    def test_switch_to_accurate_model(self):
        result = settings_control.run({"utterance": "use accurate model"})
        assert "medium" in result
        assert config.WHISPER_MODEL == "medium"

    def test_switch_to_better_model(self):
        result = settings_control.run({"utterance": "switch to better model"})
        assert "medium" in result
        assert config.WHISPER_MODEL == "medium"

    def test_switch_to_default_model(self):
        config.WHISPER_MODEL = "tiny.en"
        result = settings_control.run({"utterance": "switch to default model"})
        assert "small" in result
        assert config.WHISPER_MODEL == "small"

    def test_reset_model(self):
        config.WHISPER_MODEL = "medium"
        result = settings_control.run({"utterance": "reset model"})
        assert "small" in result
        assert config.WHISPER_MODEL == "small"

    def test_query_current_model(self):
        config.WHISPER_MODEL = "small.en"
        result = settings_control.run({"utterance": "what model are you using"})
        assert "small.en" in result
        assert "English-only" in result

    def test_query_multilingual_model(self):
        config.WHISPER_MODEL = "medium"
        result = settings_control.run({"utterance": "which model"})
        assert "medium" in result
        assert "multilingual" in result

    def test_german_model_query(self):
        result = settings_control.run({"utterance": "welches modell"})
        assert "model" in result.lower() or "modell" in result.lower()

    def test_german_faster_model(self):
        result = settings_control.run({"utterance": "wechsle zum schnelleren modell"})
        assert "tiny.en" in result
        assert config.WHISPER_MODEL == "tiny.en"


# ---------------------------------------------------------------------------
# PA-64: settings_control skill — language switching
# ---------------------------------------------------------------------------
class TestSettingsControlLanguage:
    def setup_method(self):
        config.WHISPER_MODEL = "small.en"
        config.WHISPER_LANGUAGE = "en"

    def test_switch_to_german(self):
        result = settings_control.run({"utterance": "speak german"})
        assert "de" in result
        assert config.WHISPER_LANGUAGE == "de"

    def test_switch_to_english(self):
        config.WHISPER_LANGUAGE = "de"
        result = settings_control.run({"utterance": "speak english"})
        assert "en" in result
        assert config.WHISPER_LANGUAGE == "en"

    def test_sprich_deutsch(self):
        result = settings_control.run({"utterance": "sprich deutsch"})
        assert config.WHISPER_LANGUAGE == "de"

    def test_auto_detect(self):
        result = settings_control.run({"utterance": "auto detect language"})
        assert "automatic" in result.lower()
        assert config.WHISPER_LANGUAGE == "auto"

    def test_switch_language_to_english(self):
        result = settings_control.run({"utterance": "switch language to english"})
        assert config.WHISPER_LANGUAGE == "en"

    def test_query_language(self):
        config.WHISPER_LANGUAGE = "en"
        result = settings_control.run({"utterance": "what language"})
        assert "en" in result

    def test_query_auto_language(self):
        config.WHISPER_LANGUAGE = "auto"
        result = settings_control.run({"utterance": "which language"})
        assert "automatic" in result.lower()

    def test_unknown_language(self):
        result = settings_control.run({"utterance": "speak klingon"})
        assert "don't know" in result.lower() or "support" in result.lower()

    def test_runtime_only_notice(self):
        result = settings_control.run({"utterance": "switch to faster model"})
        assert "restart" in result.lower()

    def test_self_test(self):
        assert settings_control.self_test() is True


# ---------------------------------------------------------------------------
# PA-64: config actually changes at runtime
# ---------------------------------------------------------------------------
class TestSettingsRuntimeModification:
    def setup_method(self):
        config.WHISPER_MODEL = "small.en"
        config.WHISPER_LANGUAGE = "en"

    def test_model_persists_across_calls(self):
        settings_control.run({"utterance": "switch to faster model"})
        assert config.WHISPER_MODEL == "tiny.en"
        # Query should reflect the change
        result = settings_control.run({"utterance": "what model are you using"})
        assert "tiny.en" in result

    def test_language_persists_across_calls(self):
        settings_control.run({"utterance": "speak german"})
        assert config.WHISPER_LANGUAGE == "de"
        result = settings_control.run({"utterance": "what language"})
        assert "de" in result


# ---------------------------------------------------------------------------
# PA-81: update_check skill — version comparison
# ---------------------------------------------------------------------------
class TestUpdateCheckVersionCompare:
    def test_equal_versions(self):
        assert update_check._compare_versions("0.12.0", "0.12.0") == 0

    def test_local_older(self):
        assert update_check._compare_versions("0.11.0", "0.12.0") == -1

    def test_local_newer(self):
        assert update_check._compare_versions("0.13.0", "0.12.0") == 1

    def test_patch_difference(self):
        assert update_check._compare_versions("0.12.0", "0.12.1") == -1

    def test_major_difference(self):
        assert update_check._compare_versions("0.12.0", "1.0.0") == -1

    def test_different_length_versions(self):
        assert update_check._compare_versions("0.12", "0.12.0") == 0
        assert update_check._compare_versions("0.12.0", "0.12") == 0


# ---------------------------------------------------------------------------
# PA-81: update_check skill — run() with mocked network
# ---------------------------------------------------------------------------
class TestUpdateCheckRun:
    def test_version_query(self):
        with patch.object(update_check, "VERSION_FILE", Path(__file__).parent.parent / "VERSION"):
            result = update_check.run({"utterance": "what version"})
            assert "1.0.0" in result

    def test_up_to_date(self):
        with patch.object(update_check, "_read_local_version", return_value="0.12.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value="0.12.0"):
            result = update_check.run({"utterance": "check for updates"})
            assert "up to date" in result.lower()

    def test_update_available(self):
        with patch.object(update_check, "_read_local_version", return_value="0.11.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value="0.12.0"):
            result = update_check.run({"utterance": "check for updates"})
            assert "update available" in result.lower()
            assert "0.12.0" in result

    def test_running_newer(self):
        with patch.object(update_check, "_read_local_version", return_value="0.13.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value="0.12.0"):
            result = update_check.run({"utterance": "check for updates"})
            assert "newer" in result.lower()

    def test_network_error(self):
        with patch.object(update_check, "_read_local_version", return_value="0.12.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value=None):
            result = update_check.run({"utterance": "check for updates"})
            assert "couldn't check" in result.lower() or "no internet" in result.lower()

    def test_unknown_version(self):
        with patch.object(update_check, "_read_local_version", return_value="unknown"):
            result = update_check.run({"utterance": "check for updates"})
            assert "couldn't determine" in result.lower() or "missing" in result.lower()

    def test_self_test(self):
        assert update_check.self_test() is True


# ---------------------------------------------------------------------------
# PA-81: update_check — get_version_info()
# ---------------------------------------------------------------------------
class TestGetVersionInfo:
    def test_info_structure(self):
        with patch.object(update_check, "_read_local_version", return_value="0.12.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value="0.12.0"):
            info = update_check.get_version_info()
            assert "version" in info
            assert "latest" in info
            assert "update_available" in info
            assert info["version"] == "0.12.0"
            assert info["update_available"] is False

    def test_info_update_available(self):
        with patch.object(update_check, "_read_local_version", return_value="0.11.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value="0.12.0"):
            info = update_check.get_version_info()
            assert info["update_available"] is True

    def test_info_network_failure(self):
        with patch.object(update_check, "_read_local_version", return_value="0.12.0"), \
             patch.object(update_check, "_fetch_latest_version", return_value=None):
            info = update_check.get_version_info()
            assert info["latest"] is None
            assert info["update_available"] is False


# ---------------------------------------------------------------------------
# PA-81: GET /api/version endpoint
# ---------------------------------------------------------------------------
class TestApiVersionEndpoint:
    def test_version_endpoint_returns_200(self, client):
        with patch("backend.skills.update_check._read_local_version", return_value="0.12.0"), \
             patch("backend.skills.update_check._fetch_latest_version", return_value="0.12.0"):
            r = client.get("/api/version")
            assert r.status_code == 200

    def test_version_endpoint_shape(self, client):
        with patch("backend.skills.update_check._read_local_version", return_value="0.12.0"), \
             patch("backend.skills.update_check._fetch_latest_version", return_value="0.12.0"):
            data = client.get("/api/version").json()
            assert "version" in data
            assert "latest" in data
            assert "update_available" in data
            assert isinstance(data["update_available"], bool)

    def test_version_endpoint_update_available(self, client):
        with patch("backend.skills.update_check._read_local_version", return_value="0.11.0"), \
             patch("backend.skills.update_check._fetch_latest_version", return_value="0.12.0"):
            data = client.get("/api/version").json()
            assert data["update_available"] is True
            assert data["version"] == "0.11.0"
            assert data["latest"] == "0.12.0"

    def test_version_endpoint_up_to_date(self, client):
        with patch("backend.skills.update_check._read_local_version", return_value="0.12.0"), \
             patch("backend.skills.update_check._fetch_latest_version", return_value="0.12.0"):
            data = client.get("/api/version").json()
            assert data["update_available"] is False
