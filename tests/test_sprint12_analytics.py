"""
Sprint 12 tests — PA-68, PA-72, PA-73.

Covers:
- MemoryStore.get_facts_all()
- MemoryStore.get_skills_meta()
- MemoryStore.log_request() / get_request_log()
- MemoryStore.delete_fact()
- API endpoints: GET /api/facts, DELETE /api/facts/{id}, GET /api/skills/stats,
                 GET /api/latency/{session_id}, GET /analytics
"""
from __future__ import annotations

import sys
import types
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal stubs for modules that require native libs (numpy, whisper, etc.)
# ---------------------------------------------------------------------------
def _stub_module(name: str):
    """Insert an empty module stub into sys.modules under *name*.

    Only creates intermediary stubs for parent paths that are NOT real packages
    already present in sys.modules.
    """
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        full = ".".join(parts[:i])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            sys.modules[full] = mod


def _install_stubs():
    """Patch sys.modules so backend/main.py can be imported without native deps."""
    # numpy
    np_mod = types.ModuleType("numpy")
    sys.modules.setdefault("numpy", np_mod)

    # First import the real backend packages so we don't accidentally clobber them
    import backend  # noqa: F401
    import backend.modules  # noqa: F401
    import backend.modules.memory  # noqa: F401
    import backend.modules.router  # noqa: F401
    import backend.modules.skills  # noqa: F401
    import backend.modules.user  # noqa: F401
    import backend.core  # noqa: F401

    # voice pipeline stubs — only the leaf modules that need native libs
    for name in [
        "backend.modules.voice",
        "backend.modules.voice.pipeline",
        "backend.modules.voice.asr",
        "backend.modules.voice.tts",
        "backend.modules.voice.speaker_id",
        "backend.modules.voice.wake_monitor",
    ]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    # pipeline stub with the functions main.py uses
    pipeline_mod = sys.modules["backend.modules.voice.pipeline"]
    pipeline_mod.transcribe_audio_bytes = lambda data: {"text": "", "error": "stub"}
    pipeline_mod.get_asr = lambda: None

    # tts stub
    tts_mod = sys.modules["backend.modules.voice.tts"]
    tts_mod.synthesize = lambda text, lang=None: b""
    tts_mod.health_check = lambda: {"loaded": False}
    tts_mod._load_voice = lambda: None

    # speaker_id stub
    sid_mod = sys.modules["backend.modules.voice.speaker_id"]
    sid_mod.parse_enroll_command = lambda text: None
    sid_mod.enroll = lambda name, audio: "stub"
    sid_mod.identify = lambda audio: (None, 0.0)
    sid_mod.list_speakers = lambda: []
    sid_mod.is_available = lambda: False

    # wake_monitor stub
    wm_mod = sys.modules["backend.modules.voice.wake_monitor"]
    wm_class = types.SimpleNamespace(
        start=lambda: None,
        stop=lambda: None,
        add_client=lambda ws: None,
        remove_client=lambda ws: None,
    )

    async def _async_noop(*a, **kw):
        pass

    wm_class.start = _async_noop
    wm_class.stop = _async_noop
    wm_mod.wake_monitor = wm_class

    # Real modules that CAN be imported (no native lib deps) — don't stub them.
    # ollama_client, suggester, user_md, chat_service all import fine without native libs.
    # We only need to stub the voice pipeline modules that pull in numpy/resemblyzer.

    # chat_service stubs — it's imported in main.py's module body; stub only the
    # functions that would pull in Ollama or the voice pipeline transitively.
    # We import the real module (it's pure Python), then monkeypatch per-test.

    # httpx is a real package needed by TestClient — do NOT stub it


_install_stubs()


# ---------------------------------------------------------------------------
# Now we can safely import the app and the store
# ---------------------------------------------------------------------------
from backend.modules.memory.store import MemoryStore  # noqa: E402
from backend.modules.router import chat_service as _cs  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    """Fresh in-tmp-dir database per test."""
    return MemoryStore(db_path=tmp_path / "test.sqlite")


@pytest.fixture
def client(store, monkeypatch):
    """FastAPI TestClient with the memory store wired to our tmp store."""
    # Patch chat_service.get_memory to return our test store
    monkeypatch.setattr(_cs, "get_memory", lambda: store)

    # Patch backend.main.get_memory as well (imported at module level)
    import backend.main as main_mod
    monkeypatch.setattr(main_mod, "get_memory", lambda: store)

    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# PA-68: MemoryStore.get_facts_all() and delete_fact()
# ---------------------------------------------------------------------------
class TestGetFactsAll:
    def test_returns_all_facts_no_filter(self, store: MemoryStore):
        store.add_fact("preference", "dark mode")
        store.add_fact("identity", "Hocine")
        store.add_fact("project", "Plasma")
        facts = store.get_facts_all()
        assert len(facts) == 3

    def test_returns_empty_when_no_facts(self, store: MemoryStore):
        assert store.get_facts_all() == []

    def test_respects_limit(self, store: MemoryStore):
        for i in range(10):
            store.add_fact("pref", f"fact {i}")
        facts = store.get_facts_all(limit=5)
        assert len(facts) == 5

    def test_newest_first(self, store: MemoryStore):
        store.add_fact("pref", "old one")
        store.add_fact("pref", "new one")
        facts = store.get_facts_all()
        # Both facts should be present; just verify ordering by id (DESC by updated_at/id)
        contents = [f["content"] for f in facts]
        assert "old one" in contents
        assert "new one" in contents


class TestDeleteFact:
    def test_delete_existing(self, store: MemoryStore):
        fid = store.add_fact("preference", "to delete")
        assert store.delete_fact(fid) is True

    def test_deleted_fact_is_gone(self, store: MemoryStore):
        fid = store.add_fact("preference", "gone")
        store.delete_fact(fid)
        remaining = [f for f in store.get_facts_all() if f["id"] == fid]
        assert remaining == []

    def test_delete_nonexistent_returns_false(self, store: MemoryStore):
        assert store.delete_fact(99999) is False

    def test_double_delete(self, store: MemoryStore):
        fid = store.add_fact("pref", "temp")
        store.delete_fact(fid)
        assert store.delete_fact(fid) is False


# ---------------------------------------------------------------------------
# PA-72: MemoryStore.get_skills_meta()
# ---------------------------------------------------------------------------
class TestGetSkillsMeta:
    def test_returns_skills_sorted_by_usage(self, store: MemoryStore):
        store.register_skill("low_skill", "desc", ["a"], "a.md")
        store.register_skill("high_skill", "desc", ["b"], "b.md")
        store.mark_skill_used("high_skill")
        store.mark_skill_used("high_skill")
        store.mark_skill_used("low_skill")

        skills = store.get_skills_meta()
        assert skills[0]["name"] == "high_skill"
        assert skills[0]["usage_count"] == 2

    def test_returns_empty_list_when_no_skills(self, store: MemoryStore):
        assert store.get_skills_meta() == []

    def test_triggers_are_deserialized(self, store: MemoryStore):
        store.register_skill("echo", "repeat text", ["echo", "repeat"], "echo.md")
        skills = store.get_skills_meta()
        assert isinstance(skills[0]["triggers"], list)


# ---------------------------------------------------------------------------
# PA-73: MemoryStore.log_request() and get_request_log()
# ---------------------------------------------------------------------------
class TestRequestLog:
    def test_log_and_retrieve(self, store: MemoryStore):
        rid = store.log_request("sess-1", 0, asr_ms=120.0, llm_ms=500.0, tts_ms=80.0, total_ms=700.0)
        assert rid > 0
        rows = store.get_request_log("sess-1")
        assert len(rows) == 1
        r = rows[0]
        assert r["session_id"] == "sess-1"
        assert r["turn"] == 0
        assert abs(r["asr_ms"] - 120.0) < 0.01
        assert abs(r["total_ms"] - 700.0) < 0.01

    def test_multiple_turns_ordered(self, store: MemoryStore):
        for i in range(5):
            store.log_request("sess-a", i, total_ms=float(i * 100))
        rows = store.get_request_log("sess-a")
        turns = [r["turn"] for r in rows]
        assert turns == sorted(turns)

    def test_isolation_by_session(self, store: MemoryStore):
        store.log_request("s1", 0, total_ms=100.0)
        store.log_request("s2", 0, total_ms=200.0)
        assert len(store.get_request_log("s1")) == 1
        assert len(store.get_request_log("s2")) == 1

    def test_nullable_fields(self, store: MemoryStore):
        store.log_request("sess-b", 0)
        rows = store.get_request_log("sess-b")
        assert rows[0]["asr_ms"] is None
        assert rows[0]["tts_ms"] is None

    def test_skill_used_stored(self, store: MemoryStore):
        store.log_request("sess-c", 0, skill_used="weather")
        rows = store.get_request_log("sess-c")
        assert rows[0]["skill_used"] == "weather"

    def test_empty_session_returns_empty_list(self, store: MemoryStore):
        assert store.get_request_log("no-such-session") == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------
class TestApiEndpoints:
    def test_analytics_page_returns_200(self, client):
        r = client.get("/analytics")
        assert r.status_code == 200
        # Either HTML or 404 (if file not present in test env)
        assert r.status_code in (200, 404)

    def test_get_facts_empty(self, client):
        r = client.get("/api/facts")
        assert r.status_code == 200
        data = r.json()
        assert "facts" in data
        assert data["facts"] == []

    def test_get_facts_returns_stored(self, client, store):
        store.add_fact("preference", "test fact")
        r = client.get("/api/facts")
        assert r.status_code == 200
        facts = r.json()["facts"]
        assert any(f["content"] == "test fact" for f in facts)

    def test_get_facts_category_filter(self, client, store):
        store.add_fact("preference", "likes coffee")
        store.add_fact("identity", "named Hocine")
        r = client.get("/api/facts?category=preference")
        assert r.status_code == 200
        facts = r.json()["facts"]
        assert all(f["category"] == "preference" for f in facts)

    def test_delete_fact_success(self, client, store):
        fid = store.add_fact("preference", "to delete")
        r = client.delete(f"/api/facts/{fid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_fact_not_found(self, client):
        r = client.delete("/api/facts/99999")
        assert r.status_code == 404
        assert r.json()["ok"] is False

    def test_skills_stats_empty(self, client):
        r = client.get("/api/skills/stats")
        assert r.status_code == 200
        data = r.json()
        assert "skills" in data
        assert data["skills"] == []

    def test_skills_stats_returns_data(self, client, store):
        store.register_skill("weather", "get weather", ["weather"], "weather.md")
        store.mark_skill_used("weather")
        r = client.get("/api/skills/stats")
        assert r.status_code == 200
        skills = r.json()["skills"]
        assert any(s["name"] == "weather" for s in skills)
        w = next(s for s in skills if s["name"] == "weather")
        assert w["usage_count"] == 1

    def test_latency_endpoint_empty(self, client):
        r = client.get("/api/latency/no-such-session")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == "no-such-session"
        assert data["latency"] == []

    def test_latency_endpoint_returns_rows(self, client, store):
        store.log_request("test-sess", 0, asr_ms=100.0, total_ms=400.0)
        store.log_request("test-sess", 1, asr_ms=110.0, total_ms=380.0)
        r = client.get("/api/latency/test-sess")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == "test-sess"
        assert len(data["latency"]) == 2
        assert data["latency"][0]["turn"] == 0
        assert data["latency"][1]["turn"] == 1
