"""
Ollama HTTP client for Plasma.

Uses /api/chat for multi-turn conversations. Synchronous via httpx.

Two call modes:
  chat()                  — full response, stream=False (used by skill path, tests)
  chat_first_sentence()   — streaming, returns after first sentence boundary.
                            Cuts perceived LLM latency by ~40% because TTS can
                            start as soon as one sentence is ready.
"""
from __future__ import annotations
import json
import logging
import re
import httpx
from backend.core.config import config

log = logging.getLogger("plasma.ollama")

DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

_SENTENCE_END = re.compile(r'[.!?](?:\s|$)')


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
    return messages


def chat(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """Full blocking call — waits for the complete reply."""
    model = model or config.OLLAMA_MODEL
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": False}
    log.info(f"Ollama call (full): model={model} history_len={len(history or [])}")

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return ((data.get("message") or {}).get("content", "")).strip()


def chat_first_sentence(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    min_words: int = 4,
) -> str:
    """
    Stream tokens from Ollama. Return as soon as the first complete sentence
    arrives (detected by punctuation after >= min_words).

    Why: TTS can start the moment one sentence is ready instead of waiting
    for the full response. Saves 3-8s on the LLM path on CPU hardware.

    Falls back gracefully: if no sentence boundary is found the full
    streamed reply is returned.
    """
    model = model or config.OLLAMA_MODEL
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    messages = _build_messages(system_prompt, history, user_message)
    payload = {"model": model, "messages": messages, "stream": True}
    log.info(f"Ollama call (streaming): model={model} history_len={len(history or [])}")

    collected = ""
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = (chunk.get("message") or {}).get("content", "")
                collected += token

                # Only cut off at the first sentence if explicitly enabled — it
                # truncates real answers when the model opens with a greeting.
                if getattr(config, "CHAT_FIRST_SENTENCE_ONLY", False) and len(collected.split()) >= min_words:
                    m = _SENTENCE_END.search(collected)
                    if m:
                        first = collected[: m.end()].strip()
                        log.info(f"First sentence ready ({len(first)} chars), stopping stream")
                        return first

                if chunk.get("done"):
                    break

    return collected.strip()


def list_installed_models() -> list[str]:
    """Names of models installed in Ollama (empty list if unreachable)."""
    url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        return []


def _model_installed(name: str, installed: list[str]) -> bool:
    """Match a configured model against installed names, tolerating :latest."""
    if not name:
        return True  # nothing configured → nothing to warn about
    name = name.strip()
    bare = name.split(":")[0]
    for m in installed:
        if m == name or m.split(":")[0] == bare:
            return True
    return False


def check_configured_models() -> list[str]:
    """Return human-readable warnings for configured models that aren't pulled.

    Empty list means all good (or Ollama unreachable → we stay quiet, the chat
    path already surfaces connection errors).
    """
    installed = list_installed_models()
    if not installed:
        return []
    warnings: list[str] = []
    checks = [
        ("OLLAMA_MODEL", config.OLLAMA_MODEL),
        ("LOCATE_VISION_OLLAMA_MODEL", getattr(config, "LOCATE_VISION_OLLAMA_MODEL", "")),
    ]
    for var, model in checks:
        if model and not _model_installed(model, installed):
            warnings.append(
                f"{var}='{model}' is not installed in Ollama. "
                f"Run: ollama pull {model}   (installed: {', '.join(installed) or 'none'})"
            )
    return warnings


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
