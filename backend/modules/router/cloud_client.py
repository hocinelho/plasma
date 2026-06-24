"""
PA-29 — Provider-agnostic cloud LLM client for Plasma.
PA-32 — Adds Claude (Anthropic) as a second, natively-supported provider.

Default mode (CLOUD_PROVIDER=openai) uses any OpenAI-compatible
/chat/completions endpoint over httpx:
  - Google Gemini   https://generativelanguage.googleapis.com/v1beta/openai/
  - Cerebras        https://api.cerebras.ai/v1
  - OpenRouter      https://openrouter.ai/api/v1
  - Groq            https://api.groq.com/openai/v1

CLOUD_PROVIDER=anthropic switches to Claude's native Messages API
(POST https://api.anthropic.com/v1/messages) — different auth header
(x-api-key, not Bearer), a top-level "system" field instead of a system
message, and a content-block response shape instead of choices[].message.
Anthropic has no OpenAI-style /chat/completions endpoint, so it can't be
reached through the generic path above no matter what CLOUD_BASE_URL is set
to; it needs its own request/response handling, kept here so chat_service.py
doesn't need to know which provider is active.

PII is redacted from every outbound message via pii_redactor.redact_messages().

Two modes (mirrors ollama_client interface):
  chat()                — full blocking response, stream=False
  chat_first_sentence() — streaming, returns on first sentence boundary
"""
from __future__ import annotations
import json
import logging
import re
import time

import httpx

from backend.core.config import config
from backend.modules.router.audit_log import log_call
from backend.modules.router.pii_redactor import redact_messages

log = logging.getLogger("plasma.cloud_client")

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_SENTENCE_END = re.compile(r"[.!?](?:\s|$|(?=[A-Z]))")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 1024


def _is_anthropic() -> bool:
    return config.CLOUD_PROVIDER == "anthropic"


def _base_url() -> str:
    """Return a normalized CLOUD_BASE_URL — fixes common misconfiguration."""
    base = config.CLOUD_BASE_URL.rstrip("/")
    # OpenRouter API is always at /api/v1 — not /free, /api, etc.
    if "openrouter.ai" in base and not base.endswith("/api/v1"):
        return "https://openrouter.ai/api/v1"
    return base


def _headers() -> dict:
    if _is_anthropic():
        return {
            "x-api-key": config.CLOUD_API_KEY,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
    return {
        "Authorization": f"Bearer {config.CLOUD_API_KEY}",
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


def _build_anthropic_request(
    system_prompt: str | None,
    history: list[dict] | None,
    user_message: str,
) -> tuple[dict | None, list[dict]]:
    """Anthropic keeps `system` outside the messages array, and only allows
    user/assistant roles inside it — build both shapes from the same redacted
    message list the OpenAI path uses, so PII redaction stays identical."""
    redacted = _build_messages(system_prompt, history, user_message)
    system_block = None
    turns: list[dict] = []
    for m in redacted:
        if m["role"] == "system":
            system_block = m["content"]
        else:
            turns.append({"role": m["role"], "content": m["content"]})
    return system_block, turns


def is_available() -> bool:
    """True if a cloud API key is configured."""
    return bool(config.CLOUD_API_KEY)


def chat(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """Full blocking cloud call — waits for the complete reply."""
    if not is_available():
        raise RuntimeError("CLOUD_API_KEY not set")

    if _is_anthropic():
        return _anthropic_chat(user_message, history, system_prompt, model)

    model = model or config.CLOUD_MODEL
    url = f"{_base_url()}/chat/completions"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": False}
    log.info(f"Cloud call (full): model={model} msgs={len(messages)}")

    started = time.monotonic()
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
        text = ((data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")).strip()
    except Exception as e:
        log_call(
            base_url=_base_url(), model=model, mode="full",
            messages=messages, response_text="",
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error", error=str(e),
        )
        raise

    log_call(
        base_url=_base_url(), model=model, mode="full",
        messages=messages, response_text=text,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return text


def _anthropic_chat(
    user_message: str,
    history: list[dict] | None,
    system_prompt: str | None,
    model: str | None,
) -> str:
    model = model or config.CLOUD_MODEL
    system_block, turns = _build_anthropic_request(system_prompt, history, user_message)
    payload = {"model": model, "max_tokens": ANTHROPIC_MAX_TOKENS, "messages": turns}
    if system_block:
        payload["system"] = system_block
    log.info(f"Cloud call (full, anthropic): model={model} msgs={len(turns)}")

    started = time.monotonic()
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(ANTHROPIC_API_URL, json=payload, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
    except Exception as e:
        log_call(
            base_url=ANTHROPIC_API_URL, model=model, mode="full",
            messages=turns, response_text="",
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error", error=str(e),
        )
        raise

    log_call(
        base_url=ANTHROPIC_API_URL, model=model, mode="full",
        messages=turns, response_text=text,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return text


def chat_first_sentence(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    min_words: int = 4,
) -> str:
    """
    Stream tokens from the cloud provider, return at the first sentence boundary.

    Early termination cuts TTS latency: we don't wait for a 3-sentence reply
    when 1 sentence is already ready.
    """
    if not is_available():
        raise RuntimeError("CLOUD_API_KEY not set")

    if _is_anthropic():
        return _anthropic_chat_first_sentence(user_message, history, system_prompt, model, min_words)

    model = model or config.CLOUD_MODEL
    url = f"{_base_url()}/chat/completions"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": True}
    log.info(f"Cloud call (stream): model={model} msgs={len(messages)}")

    started = time.monotonic()
    collected = ""
    try:
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
                            log.info(f"Cloud first sentence ready ({len(first)} chars)")
                            log_call(
                                base_url=_base_url(), model=model, mode="stream",
                                messages=messages, response_text=first,
                                latency_ms=int((time.monotonic() - started) * 1000),
                            )
                            return first
    except Exception as e:
        log_call(
            base_url=_base_url(), model=model, mode="stream",
            messages=messages, response_text=collected,
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error", error=str(e),
        )
        raise

    final = collected.strip()
    log_call(
        base_url=_base_url(), model=model, mode="stream",
        messages=messages, response_text=final,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return final


def _anthropic_chat_first_sentence(
    user_message: str,
    history: list[dict] | None,
    system_prompt: str | None,
    model: str | None,
    min_words: int,
) -> str:
    """Same early-return-on-first-sentence behavior as chat_first_sentence(),
    parsing Anthropic's SSE event stream instead of OpenAI delta chunks.
    Each `data:` line is self-describing via its own "type" field, so the
    `event:` line that precedes it doesn't need to be tracked separately."""
    model = model or config.CLOUD_MODEL
    system_block, turns = _build_anthropic_request(system_prompt, history, user_message)
    payload = {"model": model, "max_tokens": ANTHROPIC_MAX_TOKENS, "messages": turns, "stream": True}
    if system_block:
        payload["system"] = system_block
    log.info(f"Cloud call (stream, anthropic): model={model} msgs={len(turns)}")

    started = time.monotonic()
    collected = ""
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            with client.stream("POST", ANTHROPIC_API_URL, json=payload, headers=_headers()) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[len("data: "):])
                    except json.JSONDecodeError:
                        continue

                    if event.get("type") != "content_block_delta":
                        continue
                    delta = event.get("delta", {})
                    if delta.get("type") != "text_delta":
                        continue
                    token = delta.get("text", "")
                    if not token:
                        continue
                    collected += token

                    if len(collected.split()) >= min_words:
                        m = _SENTENCE_END.search(collected)
                        if m:
                            first = collected[: m.end()].strip()
                            log.info(f"Cloud first sentence ready ({len(first)} chars)")
                            log_call(
                                base_url=ANTHROPIC_API_URL, model=model, mode="stream",
                                messages=turns, response_text=first,
                                latency_ms=int((time.monotonic() - started) * 1000),
                            )
                            return first
    except Exception as e:
        log_call(
            base_url=ANTHROPIC_API_URL, model=model, mode="stream",
            messages=turns, response_text=collected,
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error", error=str(e),
        )
        raise

    final = collected.strip()
    log_call(
        base_url=ANTHROPIC_API_URL, model=model, mode="stream",
        messages=turns, response_text=final,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return final


def health_check() -> dict:
    """Quick probe: is the cloud provider reachable and is the key valid?"""
    if not is_available():
        return {"reachable": False, "error": "CLOUD_API_KEY not configured"}

    if _is_anthropic():
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(ANTHROPIC_MODELS_URL, headers=_headers())
                resp.raise_for_status()
                models = [m["id"] for m in resp.json().get("data", [])]
            return {
                "reachable": True,
                "model_present": config.CLOUD_MODEL in models,
                "available_models": models,
            }
        except Exception as e:
            return {"reachable": False, "error": str(e)}

    url = f"{_base_url()}/models"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, headers=_headers())
            resp.raise_for_status()
            models = [m["id"] for m in resp.json().get("data", [])]
        return {
            "reachable": True,
            "model_present": config.CLOUD_MODEL in models,
            "available_models": models,
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}
