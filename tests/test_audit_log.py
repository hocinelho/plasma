"""Tests for PA-30 — audit log of outbound cloud LLM calls."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_audit_path(tmp_path, monkeypatch):
    """Redirect the audit log to a tmp file for each test."""
    path = tmp_path / "audit.log"
    monkeypatch.setattr(
        "backend.modules.router.audit_log._AUDIT_PATH", path
    )
    return path


def _entries(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── basic write ──────────────────────────────────────────────────────────────

def test_log_call_appends_jsonl(fake_audit_path):
    from backend.modules.router.audit_log import log_call

    log_call(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-2.0-flash",
        mode="full",
        messages=[{"role": "user", "content": "hi"}],
        response_text="hello there.",
        latency_ms=123,
    )

    rows = _entries(fake_audit_path)
    assert len(rows) == 1
    e = rows[0]
    assert e["provider"] == "generativelanguage.googleapis.com"
    assert e["model"] == "gemini-2.0-flash"
    assert e["mode"] == "full"
    assert e["msg_count"] == 1
    assert e["prompt_chars"] == 2
    assert e["response_chars"] == len("hello there.")
    assert e["latency_ms"] == 123
    assert e["status"] == "ok"
    assert "error" not in e
    assert e["ts"].endswith("Z")


def test_log_call_records_error(fake_audit_path):
    from backend.modules.router.audit_log import log_call

    log_call(
        base_url="https://api.cerebras.ai/v1",
        model="llama-3.3-70b",
        mode="stream",
        messages=[{"role": "user", "content": "x" * 50}],
        response_text="",
        latency_ms=1500,
        status="error",
        error="429 Too Many Requests",
    )

    rows = _entries(fake_audit_path)
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "429 Too Many Requests"
    assert rows[0]["provider"] == "api.cerebras.ai"


def test_log_call_multiple_appends(fake_audit_path):
    from backend.modules.router.audit_log import log_call

    for i in range(3):
        log_call(
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.1-8b-instant",
            mode="full",
            messages=[{"role": "user", "content": f"q{i}"}],
            response_text=f"a{i}",
            latency_ms=100 + i,
        )

    rows = _entries(fake_audit_path)
    assert len(rows) == 3
    assert [r["latency_ms"] for r in rows] == [100, 101, 102]


def test_log_call_never_raises(fake_audit_path, monkeypatch):
    """audit log must never bring down the chat path."""
    from backend.modules.router import audit_log

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(audit_log, "_AUDIT_PATH", fake_audit_path)
    monkeypatch.setattr("pathlib.Path.open", boom)

    audit_log.log_call(
        base_url="https://x", model="m", mode="full",
        messages=[], response_text="", latency_ms=0,
    )


# ── read_entries ─────────────────────────────────────────────────────────────

def test_read_entries_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.modules.router.audit_log._AUDIT_PATH", tmp_path / "missing.log"
    )
    from backend.modules.router.audit_log import read_entries
    assert read_entries() == []


def test_read_entries_limit(fake_audit_path):
    from backend.modules.router.audit_log import log_call, read_entries
    for i in range(5):
        log_call(base_url="https://x", model="m", mode="full",
                 messages=[], response_text=str(i), latency_ms=i)
    out = read_entries(limit=2)
    assert len(out) == 2
    assert out[-1]["response_chars"] == 1  # last entry was response_text="4" → 1 char


# ── integration with cloud_client ────────────────────────────────────────────

def test_cloud_client_chat_writes_audit_entry(fake_audit_path):
    """End-to-end: a successful chat() call lands one ok entry in audit.log."""
    from unittest.mock import MagicMock
    from backend.modules.router.cloud_client import chat

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"choices": [{"message": {"content": "ok."}}]}

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.post.return_value = fake_resp

        chat("ping")

    rows = _entries(fake_audit_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["mode"] == "full"
    assert rows[0]["model"] == "gemini-2.0-flash"
    assert rows[0]["provider"] == "generativelanguage.googleapis.com"


def test_cloud_client_chat_writes_error_entry_on_failure(fake_audit_path):
    """If the HTTP call fails, an error entry is still written."""
    import httpx
    from backend.modules.router.cloud_client import chat

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("nope")

        with pytest.raises(httpx.ConnectError):
            chat("ping")

    rows = _entries(fake_audit_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert "nope" in rows[0]["error"]
