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


def _build_system_prompt(memory: MemoryStore, speaker: str | None = None) -> str:
    from backend.modules.user.user_md import read_user_md

    base = (
        "You are Plasma, a helpful voice assistant. "
        "Answer the user's question directly and correctly. "
        "Do NOT greet the user or say their name, and do NOT recite facts about "
        "them, unless they explicitly ask. No preamble, no apologies, no emoji. "
        "Be concise for simple questions, but give COMPLETE answers when needed: "
        "if asked for an equation, formula, definition, list, or explanation, "
        "provide the actual content — e.g. write out the equations, not just a "
        "description of them. Write mathematics in LaTeX: $$...$$ for a displayed "
        "equation and $...$ for inline math. If you don't know, say so briefly."
    )
    if speaker:
        base += f" (You are talking to {speaker}, but only use their name if asked.)"

    user_md = read_user_md(user=speaker)
    if user_md:
        return (
            f"{base}\n\n--- Background on the user (use ONLY when relevant; "
            f"never greet with it) ---\n{user_md}"
        )

    facts = memory.get_facts(limit=20, user=speaker)
    if facts:
        fact_lines = "\n".join(f"- ({f['category']}) {f['content']}" for f in facts)
        return (
            f"{base}\n\nBackground facts (use ONLY when relevant, never recite):\n{fact_lines}"
        )

    return base


def _llm_reply(user_message: str, history: list[dict], system_prompt: str) -> str:
    """Try cloud LLM first (PA-29, provider-agnostic), fall back to Ollama (PA-31)."""
    from backend.core.config import config
    from backend.modules.router.cloud_client import (
        chat_first_sentence as _cloud_chat,
        is_available as cloud_available,
    )

    # CLOUD_CHAT_ENABLED=false keeps CHAT on the local model even when a cloud key
    # is set — so the cloud quota is saved for vision (avoids 429 rate limits).
    if cloud_available() and getattr(config, "CLOUD_CHAT_ENABLED", True):
        try:
            reply = _cloud_chat(
                user_message=user_message,
                history=history,
                system_prompt=system_prompt,
            )
            log.info("LLM source: cloud")
            return reply
        except Exception as e:
            log.warning(f"Cloud LLM failed, falling back to Ollama: {e}")

    try:
        reply = _ollama_chat(
            user_message=user_message,
            history=history,
            system_prompt=system_prompt,
        )
        log.info("LLM source: Ollama local")
        return reply
    except Exception as e:
        return _ollama_error_reply(e)


def _ollama_error_reply(e: Exception) -> str:
    """Turn an Ollama failure into a spoken, actionable message (never a 500)."""
    from backend.core.config import config
    model = config.OLLAMA_MODEL
    msg = str(e)
    # 404 = model not pulled; connection error = Ollama not running.
    if "404" in msg or "not found" in msg.lower():
        log.warning("Ollama model '%s' not found: %s", model, e)
        return (
            f"The model {model} isn't installed. On your computer run: "
            f"ollama pull {model} — then try again."
        )
    if "connect" in msg.lower() or "refused" in msg.lower() or "timed out" in msg.lower():
        log.warning("Ollama unreachable: %s", e)
        return (
            "I can't reach the local model server. Make sure Ollama is running "
            "(start the Ollama app), then try again."
        )
    log.warning("Ollama chat failed: %s", e)
    return "Sorry, I hit a problem reaching the language model. Please try again."


def handle_chat(
    session_id: str,
    user_message: str,
    language: str = "en",
    speaker: str | None = None,
) -> str:
    memory = get_memory()
    memory.add_message(session_id, "user", user_message)

    # 0. Pending intent — resume multi-step skill conversation
    try:
        registry = get_registry()
        pending = memory.get_facts(category="pending_intent", limit=1)
        if pending:
            fact = pending[0]
            skill_name = fact["content"].split(":")[0]
            skill = registry.get(skill_name)
            if skill:
                memory.delete_fact(fact["id"])
                log.info(f"Pending intent → {skill_name} for utterance: {user_message!r}")
                reply = skill.invoke({
                    "utterance": user_message,
                    "session_id": session_id,
                    "language": language,
                    "speaker": speaker,
                })
                memory.add_message(session_id, "assistant", reply)
                memory.mark_skill_used(skill.name, success=True)
                return reply
    except Exception as e:
        log.warning(f"Pending intent check failed: {e}")

    # 1. Try skills first
    try:
        registry = get_registry()
        skill = registry.find_by_trigger(user_message)
        if skill:
            log.info(f"Skill match: {skill.name} for utterance: {user_message!r}")
            reply = skill.invoke({
                "utterance": user_message,
                "session_id": session_id,
                "language": language,
                "speaker": speaker,
            })
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
    system_prompt = _build_system_prompt(memory, speaker=speaker)
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
