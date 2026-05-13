"""
Plasma chat service — glues memory, skills, suggester, and LLM.

Flow:
1. Save incoming user message to memory
2. Try a SKILL via keyword triggers — if hit, run it (fast path)
3. Otherwise call LLM:
   a. If GROQ_API_KEY is set → Groq cloud (PA-29, ~1s)
   b. If Groq fails or key absent → Ollama local (PA-31 fallback)
4. Pass utterance to suggester (counts patterns, may propose a skill)
5. Append nudge to reply if a proposal was just created
6. Save assistant reply
"""
from __future__ import annotations
import logging
from backend.modules.memory.store import MemoryStore
from backend.modules.router.ollama_client import chat_first_sentence as _ollama_chat
from backend.modules.skills.registry import get_registry
from backend.modules.skills.suggester import get_suggester

log = logging.getLogger("plasma.chat_service")

_memory: MemoryStore | None = None


def get_memory() -> MemoryStore:
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

    facts = memory.get_facts(limit=20)
    if facts:
        fact_lines = "\n".join(f"- ({f['category']}) {f['content']}" for f in facts)
        return f"{base}\n\nKnown facts about the user:\n{fact_lines}"

    return base


def _llm_reply(user_message: str, history: list[dict], system_prompt: str) -> str:
    """Try Groq cloud first (PA-29), fall back to Ollama (PA-31)."""
    from backend.modules.router.cloud_client import (
        chat_first_sentence as _groq_chat,
        is_available as groq_available,
    )

    if groq_available():
        try:
            reply = _groq_chat(
                user_message=user_message,
                history=history,
                system_prompt=system_prompt,
            )
            log.info("LLM source: Groq cloud")
            return reply
        except Exception as e:
            log.warning(f"Groq failed, falling back to Ollama: {e}")

    reply = _ollama_chat(
        user_message=user_message,
        history=history,
        system_prompt=system_prompt,
    )
    log.info("LLM source: Ollama local")
    return reply


def handle_chat(session_id: str, user_message: str) -> str:
    memory = get_memory()
    memory.add_message(session_id, "user", user_message)

    # 1. Try skills first
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

    # 2. LLM path (Groq → Ollama)
    full_history = memory.get_conversation(session_id, limit=20)
    history_for_api = [
        {"role": m["role"], "content": m["content"]} for m in full_history[:-1]
    ]
    system_prompt = _build_system_prompt(memory)
    reply = _llm_reply(user_message, history_for_api, system_prompt)

    # 3. Suggester: count patterns, maybe propose a skill
    try:
        nudge = get_suggester().record_fallback(user_message)
        if nudge:
            reply = f"{reply}{nudge}"
    except Exception as e:
        log.warning(f"Suggester failed: {e}")

    memory.add_message(session_id, "assistant", reply)
    log.info(f"LLM reply: session={session_id} reply_len={len(reply)}")
    return reply
