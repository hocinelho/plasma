"""
Plasma chat service — glues memory + local Ollama.

Flow:
1. Save incoming user message to memory
2. Load last N turns of conversation for this session
3. Build a system prompt from known facts
4. Call Ollama
5. Save the assistant reply
6. Return the reply

Later steps (9+) will add cloud escalation + PII redaction.
"""
from __future__ import annotations
import logging
from backend.modules.memory.store import MemoryStore
from backend.modules.router.ollama_client import chat as ollama_chat

log = logging.getLogger("plasma.chat_service")

_memory: MemoryStore | None = None


def get_memory() -> MemoryStore:
    """Process-wide singleton memory store (SQLite handles concurrency fine)."""
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


def _build_system_prompt(memory: MemoryStore) -> str:
    facts = memory.get_facts(limit=20)
    base = (
         "You are Plasma, a local-first voice assistant. "
        "Keep replies SHORT — usually 1 to 2 sentences, max 40 words. "
        "Be direct and friendly. No preamble, no apologies, no emoji. "
        "If the user asks a simple question, answer in one sentence."
    )
    if not facts:
        return base
    fact_lines = "\n".join(f"- ({f['category']}) {f['content']}" for f in facts)
    return f"{base}\n\nKnown facts about the user and their context:\n{fact_lines}"


def handle_chat(session_id: str, user_message: str) -> str:
    memory = get_memory()

    # 1. Save the user message
    memory.add_message(session_id, "user", user_message)

    # 2. Load history (includes the just-saved message; drop it for the API call)
    full_history = memory.get_conversation(session_id, limit=20)
    history_for_api = [
        {"role": m["role"], "content": m["content"]} for m in full_history[:-1]
    ]

    # 3. Build system prompt with facts
    system_prompt = _build_system_prompt(memory)

    # 4. Call Ollama
    reply = ollama_chat(
        user_message=user_message,
        history=history_for_api,
        system_prompt=system_prompt,
    )

    # 5. Save the assistant reply
    memory.add_message(session_id, "assistant", reply)

    log.info(f"Chat turn: session={session_id} reply_len={len(reply)}")
    return reply