"""
Plasma chat service — glues memory, skills, and Ollama.

Flow:
1. Save incoming user message to memory
2. Try to match a SKILL via keyword triggers
   - If matched: run the skill, return its reply fast (no LLM call)
3. Otherwise, fall back to Ollama (with memory injection)
4. Save the assistant reply
5. Return the reply

Skills > Ollama for speed. Ollama > nothing for flexibility.
"""
from __future__ import annotations
import logging
from backend.modules.memory.store import MemoryStore
from backend.modules.router.ollama_client import chat as ollama_chat
from backend.modules.skills.registry import get_registry

log = logging.getLogger("plasma.chat_service")

_memory: MemoryStore | None = None


def get_memory() -> MemoryStore:
    """Process-wide singleton memory store (SQLite handles concurrency fine)."""
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


def _build_system_prompt(memory: MemoryStore) -> str:
    from backend.modules.user.user_md import read_user_md

    base = (
        "You are Plasma, a local-first voice assistant. "
        "Keep replies SHORT — usually 1 to 2 sentences, max 40 words. "
        "Be direct and friendly. No preamble, no apologies, no emoji. "
        "If the user asks a simple question, answer in one sentence."
    )

    user_md = read_user_md()
    if user_md:
        return f"{base}\n\n--- About the user (from USER.md) ---\n{user_md}"

    # Fallback: list facts directly if USER.md doesn't exist yet
    facts = memory.get_facts(limit=20)
    if facts:
        fact_lines = "\n".join(f"- ({f['category']}) {f['content']}" for f in facts)
        return f"{base}\n\nKnown facts about the user:\n{fact_lines}"

    return base


def handle_chat(session_id: str, user_message: str) -> str:
    memory = get_memory()

    # 1. Save the user message
    memory.add_message(session_id, "user", user_message)

    # 2. Try the skill registry first
    try:
        registry = get_registry()
        skill = registry.find_by_trigger(user_message)
        if skill:
            log.info(f"Skill match: {skill.name} for utterance: {user_message!r}")
            reply = skill.invoke({"utterance": user_message, "session_id": session_id})
            memory.add_message(session_id, "assistant", reply)
            memory.mark_skill_used(skill.name, success=True)
            return reply
    except Exception as e:
        log.warning(f"Skill routing failed, falling back to LLM: {e}")

    # 3. No skill matched — fall back to Ollama
    full_history = memory.get_conversation(session_id, limit=20)
    history_for_api = [
        {"role": m["role"], "content": m["content"]} for m in full_history[:-1]
    ]
    system_prompt = _build_system_prompt(memory)

    reply = ollama_chat(
        user_message=user_message,
        history=history_for_api,
        system_prompt=system_prompt,
    )

    # 4. Save the assistant reply
    memory.add_message(session_id, "assistant", reply)

    log.info(f"LLM reply: session={session_id} reply_len={len(reply)}")
    return reply