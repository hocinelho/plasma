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

# connect is deliberately long: while Ollama loads a big model it may not
# service new connections, which is indistinguishable from it being down.
DEFAULT_TIMEOUT = httpx.Timeout(
    config.OLLAMA_READ_TIMEOUT, connect=config.OLLAMA_CONNECT_TIMEOUT
)

_SENTENCE_END = re.compile(r'[.!?](?:\s|$)')

# Hybrid-reasoning models: they emit a <think> block before the answer, and
# it is spent from the SAME num_predict budget. At the shipped cap of 160
# tokens that is the whole allowance — the thinking uses it up, strip_reasoning
# removes the thinking, and what reaches the user is the tail end of an answer
# that never got written. Measured on a real session: replies of 31, 50 and 20
# characters, and "why…" or "what do you think…" questions — the ones that
# make a model think longest — came back emptiest of all. It reads exactly
# like a model that has nothing to say.
#
# For a voice assistant the answer is not a bigger budget: on a laptop CPU,
# tripling the tokens triples the wait. The answer is to not think out loud at
# all. qwen3 takes "/no_think" as a soft switch that skips the block, so the
# whole budget goes to the reply and she is faster as well as fuller.
_REASONING_MODELS = ("qwen3", "deepseek-r1", "magistral", "phi4-reasoning",
                     "qwq", "exaone-deep")
NO_THINK = "/no_think"


def is_reasoning_model(name: str) -> bool:
    """True if this model emits a chain of thought unless told not to."""
    n = (name or "").lower()
    return any(tag in n for tag in _REASONING_MODELS)


def thinking_disabled(model: str) -> bool:
    """Whether to ask this model to skip its visible reasoning.

    Reads the existing OLLAMA_THINK knob rather than adding a second one.
    Unset (the default) means "decide from the model", and for a voice
    assistant that means off wherever it exists: the deliberation is never
    shown and never spoken, so it buys nothing and costs both the token
    budget and the wait. Set OLLAMA_THINK=true to keep it — worth it on a
    fast machine, where the extra quality on hard questions is free.
    """
    mode = (getattr(config, "OLLAMA_THINK", "") or "").strip().lower()
    if mode in ("true", "1", "yes", "on"):
        return False
    if mode in ("false", "0", "no", "off"):
        return True
    return is_reasoning_model(model)


def _runtime_options() -> dict:
    """The per-request knobs that decide how fast she feels.

    `keep_alive` is the one that matters most and is easiest to miss. Ollama
    unloads an idle model after five minutes by default, so the startup warm-up
    only helps the first few questions — ask her something after lunch and you
    pay the full model load again, which on a 14B is tens of seconds and reads
    as "she froze". Sending it on every request keeps her resident.

    `num_predict` caps how much she can say. A voice assistant that answers in
    400 words is not thorough, it is slow: every extra word costs generation
    time AND speech time, twice over.
    """
    opts: dict = {}
    if config.OLLAMA_NUM_PREDICT > 0:
        opts["num_predict"] = config.OLLAMA_NUM_PREDICT
    if config.OLLAMA_NUM_CTX > 0:
        opts["num_ctx"] = config.OLLAMA_NUM_CTX
    return opts


def _payload(model: str, messages: list[dict], stream: bool) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
    }
    opts = _runtime_options()
    if opts:
        payload["options"] = opts
    # Only sent when explicitly configured: Ollama errors on this field for
    # models that have no thinking mode, which would break every non-reasoning
    # model to tidy up one.
    if config.OLLAMA_THINK in ("false", "0", "no", "off"):
        payload["think"] = False
    elif config.OLLAMA_THINK in ("true", "1", "yes", "on"):
        payload["think"] = True
    return payload


def _build_messages(
    system_prompt: str | None,
    history: list[dict] | None,
    user_message: str,
    model: str | None = None,
) -> list[dict]:
    messages: list[dict] = []
    if system_prompt or thinking_disabled(model or config.OLLAMA_MODEL):
        system_prompt = system_prompt or ""
        if thinking_disabled(model or config.OLLAMA_MODEL):
            # Inert text to any model that does not know it, so this needs no
            # version check — unlike Ollama's think:false, which is rejected
            # outright by models without a thinking mode.
            system_prompt = f"{system_prompt}\n\n{NO_THINK}".strip()
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
    messages = _build_messages(system_prompt, history, user_message, model)
    payload = _payload(model, messages, stream=False)
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
    messages = _build_messages(system_prompt, history, user_message, model)
    payload = _payload(model, messages, stream=True)
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
