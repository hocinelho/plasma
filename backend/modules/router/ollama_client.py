"""
Ollama HTTP client for Plasma.

Uses /api/chat for multi-turn conversations. Synchronous via httpx for simplicity;
FastAPI routes can call this from a thread or inside async with no issues
because httpx's Client is fine to call from sync code and our endpoints are short-lived.
"""
from __future__ import annotations
import logging
import httpx
from backend.core.config import config

log = logging.getLogger("plasma.ollama")

# Generous timeout — CPU inference of a 3B model can take 20–60s on first tokens
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


def chat(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """
    Send a message to Ollama /api/chat and return the assistant's reply.

    Args:
        user_message: the new user turn (string)
        history:      list of {"role": "user"|"assistant"|"system", "content": str}
        system_prompt: optional system prompt — prepended if provided
        model:        override the model; defaults to config.OLLAMA_MODEL
    """
    model = model or config.OLLAMA_MODEL
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for m in history:
            if m.get("role") in ("user", "assistant", "system"):
                messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,  # we'll add streaming later
    }

    log.info(f"Ollama call: model={model} history_len={len(history or [])}")

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Ollama /api/chat returns: { "message": { "role": "assistant", "content": "..." }, ... }
    content = (data.get("message") or {}).get("content", "")
    return content.strip()


def health_check() -> dict:
    """Quick probe: is Ollama reachable and is our model available?"""
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        return {
            "reachable": True,
            "model_present": config.OLLAMA_MODEL in models,
            "available_models": models,
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}