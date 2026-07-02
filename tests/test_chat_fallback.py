"""Ollama failures should produce a friendly reply, not a 500."""
from unittest.mock import patch

from backend.modules.router import chat_service as cs


def test_model_not_found_message():
    out = cs._ollama_error_reply(Exception("Client error '404 Not Found' for url .../api/chat"))
    assert "ollama pull" in out.lower()


def test_connection_error_message():
    out = cs._ollama_error_reply(Exception("Connection refused"))
    assert "ollama" in out.lower() and "running" in out.lower()


def test_generic_error_message():
    out = cs._ollama_error_reply(Exception("kaboom"))
    assert "problem" in out.lower()


def test_llm_reply_catches_ollama_404():
    # Cloud unavailable → Ollama path; Ollama raises 404 → friendly message.
    with patch("backend.modules.router.cloud_client.is_available", return_value=False), \
         patch.object(cs, "_ollama_chat", side_effect=Exception("404 Not Found")):
        out = cs._llm_reply("hi", [], "sys")
    assert "ollama pull" in out.lower()
