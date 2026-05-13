"""Tests for PA-29 — provider-agnostic cloud client (all HTTP mocked, no real API call)."""
from __future__ import annotations
from unittest.mock import MagicMock, patch
import json
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_full_response(content: str) -> MagicMock:
    """Fake httpx response for stream=False."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return resp


def _sse_lines(content: str) -> list[str]:
    """Fake SSE lines for a streaming response."""
    words = content.split()
    lines = []
    for w in words:
        chunk = {"choices": [{"delta": {"content": w + " "}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")
    return lines


# ── is_available ──────────────────────────────────────────────────────────────

def test_is_available_false_when_no_key():
    from backend.modules.router.cloud_client import is_available
    with patch("backend.modules.router.cloud_client.config") as cfg:
        cfg.CLOUD_API_KEY = ""
        assert is_available() is False


def test_is_available_true_when_key_set():
    from backend.modules.router.cloud_client import is_available
    with patch("backend.modules.router.cloud_client.config") as cfg:
        cfg.CLOUD_API_KEY = "test_key"
        assert is_available() is True


# ── chat (blocking) ───────────────────────────────────────────────────────────

def test_chat_raises_when_no_key():
    from backend.modules.router.cloud_client import chat
    with patch("backend.modules.router.cloud_client.config") as cfg:
        cfg.CLOUD_API_KEY = ""
        with pytest.raises(RuntimeError, match="CLOUD_API_KEY not set"):
            chat("hello")


def test_chat_returns_content(tmp_path):
    from backend.modules.router.cloud_client import chat

    fake_resp = _make_full_response("Paris is the capital of France.")

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.post.return_value = fake_resp

        result = chat("What is the capital of France?")

    assert result == "Paris is the capital of France."


def test_chat_strips_whitespace():
    from backend.modules.router.cloud_client import chat

    fake_resp = _make_full_response("  Hello world.  ")

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.post.return_value = fake_resp

        assert chat("hi") == "Hello world."


# ── chat_first_sentence (streaming) ──────────────────────────────────────────

def test_chat_first_sentence_raises_when_no_key():
    from backend.modules.router.cloud_client import chat_first_sentence
    with patch("backend.modules.router.cloud_client.config") as cfg:
        cfg.CLOUD_API_KEY = ""
        with pytest.raises(RuntimeError):
            chat_first_sentence("hello")


def test_chat_first_sentence_returns_first_sentence():
    from backend.modules.router.cloud_client import chat_first_sentence

    lines = _sse_lines("It is sunny today. Tomorrow will be rainy and cold.")

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.raise_for_status = MagicMock()
    mock_stream.iter_lines = MagicMock(return_value=iter(lines))

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.stream.return_value = mock_stream

        result = chat_first_sentence("What's the weather?", min_words=3)

    assert result.endswith(".")
    assert "rainy" not in result  # only first sentence


# ── PII redaction is applied ──────────────────────────────────────────────────

def test_chat_redacts_pii_before_sending():
    from backend.modules.router.cloud_client import chat

    fake_resp = _make_full_response("Got it.")
    captured = {}

    def fake_post(url, json=None, headers=None, **kw):
        captured["payload"] = json
        return fake_resp

    with patch("backend.modules.router.cloud_client.config") as cfg, \
         patch("backend.modules.router.cloud_client.httpx.Client") as mock_client:
        cfg.CLOUD_API_KEY = "test_key"
        cfg.CLOUD_MODEL = "gemini-2.0-flash"
        cfg.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        mock_client.return_value.__enter__.return_value.post.side_effect = fake_post

        chat("my email is test@example.com")

    messages = captured["payload"]["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "@" not in user_content
    assert "[EMAIL]" in user_content
