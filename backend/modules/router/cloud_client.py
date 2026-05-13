"""
PA-29 — Groq cloud LLM client for Plasma.

Uses Groq's OpenAI-compatible /chat/completions endpoint over httpx.
PII is redacted from every outbound message via pii_redactor.redact_messages().

Two modes (mirrors ollama_client interface):
  chat()                — full blocking response, stream=False
  chat_first_sentence() — streaming, returns on first sentence boundary

Falls back gracefully: if the API key is missing or the call fails, the
caller (chat_service) catches the exception and falls back to Ollama.
"""
from __future__ import annotations
import json
import logging
import re

import httpx

from backend.core.config import config
from backend.modules.router.pii_redactor import redact_messages

log = logging.getLogger("plasma.cloud_client")

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _build_messages(
    system_prompt: str | None,
    history: list[dict] | None,
    user_message: str,
) -> list[dict]:
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for m in (history or []):
        if m.get("role") in ("user", "assistant", "system"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    return redact_messages(messages)


def is_available() -> bool:
    """True if a Groq API key is configured."""
    return bool(config.GROQ_API_KEY)


def chat(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """Full blocking Groq call — waits for the complete reply."""
    if not is_available():
        raise RuntimeError("GROQ_API_KEY not set")

    model = model or config.GROQ_MODEL
    url = f"{config.GROQ_BASE_URL}/chat/completions"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": False}
    log.info(f"Groq call (full): model={model} msgs={len(messages)}")

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    return ((data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")).strip()


def chat_first_sentence(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    min_words: int = 4,
) -> str:
    """
    Stream tokens from Groq, return at the first sentence boundary.

    Groq runs at ~750 tok/s so the full round-trip is under 1s even
    without early termination. Early termination still cuts TTS latency
    because we don't wait for a 3-sentence reply when 1 sentence is ready.
    """
    if not is_available():
        raise RuntimeError("GROQ_API_KEY not set")

    model = model or config.GROQ_MODEL
    url = f"{config.GROQ_BASE_URL}/chat/completions"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": True}
    log.info(f"Groq call (stream): model={model} msgs={len(messages)}")

    collected = ""
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        with client.stream("POST", url, json=payload, headers=_headers()) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[len("data: "):]
                if raw.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if not token:
                    continue
                collected += token

                if len(collected.split()) >= min_words:
                    m = _SENTENCE_END.search(collected)
                    if m:
                        first = collected[: m.end()].strip()
                        log.info(f"Groq first sentence ready ({len(first)} chars)")
                        return first

    return collected.strip()


def health_check() -> dict:
    """Quick probe: is Groq reachable and is the key valid?"""
    if not is_available():
        return {"reachable": False, "error": "GROQ_API_KEY not configured"}
    url = f"{config.GROQ_BASE_URL}/models"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, headers=_headers())
            resp.raise_for_status()
            models = [m["id"] for m in resp.json().get("data", [])]
        return {
            "reachable": True,
            "model_present": config.GROQ_MODEL in models,
            "available_models": models,
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}
