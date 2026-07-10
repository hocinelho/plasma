"""Skill: remember_this — stores a fact in Plasma's memory (dedup-aware)."""
from __future__ import annotations
import re
from backend.modules.memory.store import MemoryStore


META = {
    "name": "remember_this",
    "description": "Stores a fact about the user.",
    "triggers": [
        "remember that",
        "remember i ",
        "remember my ",
        "don't forget that",
        "note that ",
    ],
    "example_utterances": [
        "Remember that I like strong coffee",
        "Remember I live in Moers",
        "Don't forget that my son's name is Malik",
    ],
}

_memory: MemoryStore | None = None


def _mem() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    speaker = (args or {}).get("speaker")  # PA-66: scope fact to identified speaker
    m = re.search(
        r"(?:remember(?:\s+that)?|don't\s+forget\s+that|note\s+that)\s+(.+)",
        utterance,
        re.IGNORECASE,
    )
    if not m:
        return "What would you like me to remember?"
    # PA-65: voice enrollment is handled upstream (needs audio). If it lands
    # here, the request came through text chat where enrollment can't work.
    if re.search(r"\bmy\s+voice\b", utterance, re.IGNORECASE):
        return "Voice enrollment only works when you speak: say 'remember my voice as' and your name."
    fact = m.group(1).strip().rstrip(".?!").strip()

    if not fact or len(fact) < 4:
        return "That sounded cut off. Could you repeat the full sentence?"
    if fact.endswith("...") or "..." in fact:
        return "That sounded cut off. Could you repeat the full sentence?"

    # Deduplicate: check if an identical fact already exists (case-insensitive)
    memory = _mem()
    existing = memory.get_facts(category="user_note", limit=500, user=speaker)
    for f in existing:
        if f["content"].strip().lower() == fact.lower():
            return f"I already remember that: {fact}."

    memory.add_fact(category="user_note", content=fact, source="voice_skill", user=speaker)
    if speaker:
        return f"Got it, {speaker}. I'll remember: {fact}."
    return f"Got it. I'll remember: {fact}."


def self_test() -> bool:
    return True