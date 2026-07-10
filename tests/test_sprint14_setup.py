"""
Sprint 14 tests — PA-82 first-run setup wizard.

Covers:
- GET /setup serves the setup page
- GET /api/setup/status returns well-formed checks + summary
- Status endpoint never 500s even when a sub-check raises
- Summary counts are internally consistent
- POST /api/setup/download/de_voice route exists (download mocked)

All native-lib modules (numpy, whisper, tts, speaker_id, wake_monitor) are
stubbed so the suite runs without numpy / resemblyzer / faster-whisper.
"""
from __future__ import annotations

import sys
import types
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

    # tts stub — provide the symbols the setup checks reach for.
    from pathlib import Path as _Path
    tts_mod = sys.modules["backend.modules.voice.tts"]
    tts_mod.synthesize = lambda text, lang=None: b""
    tts_mod.health_check = lambda: {"enabled": True, "loaded": False, "error": "stub: no voice"}
    tts_mod._load_voice = lambda: None
    tts_mod.VOICES_DIR = _Path("/nonexistent/voices")
    tts_mod._resolve_model = lambda p: _Path(p)

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


from fastapi.testclient import TestClient  # noqa: E402


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


REQUIRED_KEYS = {"id", "label", "ok", "category"}


# ---------------------------------------------------------------------------
# GET /setup
# ---------------------------------------------------------------------------
class TestSetupPage:
    def test_setup_page_returns_200(self, client):
        r = client.get("/setup")
        assert r.status_code == 200

    def test_setup_page_serves_html(self, client):
        r = client.get("/setup")
        # The real frontend/setup.html exists, so we should get HTML back.
        assert "text/html" in r.headers.get("content-type", "")
        assert "SETUP" in r.text or "setup" in r.text.lower()


# ---------------------------------------------------------------------------
# GET /api/setup/status
# ---------------------------------------------------------------------------
class TestSetupStatus:
    def test_status_returns_200(self, client):
        r = client.get("/api/setup/status")
        assert r.status_code == 200

    def test_status_has_checks_and_summary(self, client):
        data = client.get("/api/setup/status").json()
        assert isinstance(data.get("checks"), list)
        assert isinstance(data.get("summary"), dict)
        assert len(data["checks"]) > 0

    def test_every_check_has_required_keys(self, client):
        data = client.get("/api/setup/status").json()
        for check in data["checks"]:
            assert REQUIRED_KEYS.issubset(check.keys()), check
            assert check["category"] in ("required", "optional")
            assert isinstance(check["ok"], bool)

    def test_expected_check_ids_present(self, client):
        data = client.get("/api/setup/status").json()
        ids = {c["id"] for c in data["checks"]}
        expected = {
            "whisper_model", "vad_model", "tts_voice", "ollama_running",
            "ollama_model", "german_voice", "speaker_id", "cloud_llm",
        }
        assert expected.issubset(ids)

    def test_summary_keys(self, client):
        summary = client.get("/api/setup/status").json()["summary"]
        for key in ("required_ok", "required_total", "optional_ok", "optional_total", "ready"):
            assert key in summary

    def test_summary_counts_consistent(self, client):
        summary = client.get("/api/setup/status").json()["summary"]
        assert summary["required_ok"] <= summary["required_total"]
        assert summary["optional_ok"] <= summary["optional_total"]
        assert summary["required_total"] > 0
        assert isinstance(summary["ready"], bool)
        assert summary["ready"] == (summary["required_ok"] == summary["required_total"])

    def test_ready_flag_matches_required(self, client):
        data = client.get("/api/setup/status").json()
        required = [c for c in data["checks"] if c["category"] == "required"]
        all_ok = all(c["ok"] for c in required)
        assert data["summary"]["ready"] == all_ok


# ---------------------------------------------------------------------------
# Graceful failure — one broken sub-check must not 500 the endpoint
# ---------------------------------------------------------------------------
class TestStatusNeverCrashes:
    def test_broken_subcheck_does_not_500(self, client, monkeypatch):
        # Make the ollama health probe raise; the endpoint must still return 200
        # and mark that check ok=False rather than error out.
        def _boom():
            raise RuntimeError("simulated ollama explosion")

        import backend.main as main_mod
        monkeypatch.setattr(main_mod, "ollama_health", _boom)

        r = client.get("/api/setup/status")
        assert r.status_code == 200
        data = r.json()
        # ollama_running + ollama_model both depend on ollama_health -> failed
        ollama = next(c for c in data["checks"] if c["id"] == "ollama_running")
        assert ollama["ok"] is False
        assert "simulated" in (ollama["detail"] or "")

    def test_config_failure_isolated(self, client, monkeypatch):
        # Break the TTS health check; only the tts_voice row should fail.
        tts_mod = sys.modules["backend.modules.voice.tts"]

        def _boom():
            raise RuntimeError("tts kaboom")

        monkeypatch.setattr(tts_mod, "health_check", _boom)

        r = client.get("/api/setup/status")
        assert r.status_code == 200
        data = r.json()
        tts = next(c for c in data["checks"] if c["id"] == "tts_voice")
        assert tts["ok"] is False
        # Other checks unaffected — whisper_model still present and evaluated.
        assert any(c["id"] == "whisper_model" for c in data["checks"])


# ---------------------------------------------------------------------------
# POST /api/setup/download/de_voice — mocked, never hits the network
# ---------------------------------------------------------------------------
class TestDownloadDeVoice:
    def test_download_route_success_mocked(self, client, monkeypatch):
        # Patch the importable download function so no network call happens.
        import scripts.download_de_voice as dl_mod
        monkeypatch.setattr(
            dl_mod, "download_de_voice",
            lambda verbose=True: "/fake/voices/de_DE-thorsten-medium.onnx",
        )
        r = client.post("/api/setup/download/de_voice")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "de_DE-thorsten-medium.onnx" in data["path"]

    def test_download_route_reports_error(self, client, monkeypatch):
        import scripts.download_de_voice as dl_mod

        def _fail(verbose=True):
            raise RuntimeError("network down")

        monkeypatch.setattr(dl_mod, "download_de_voice", _fail)
        r = client.post("/api/setup/download/de_voice")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "network down" in data["error"]
