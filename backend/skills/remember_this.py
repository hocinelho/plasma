"""Skill: remember_this — stores a fact in Plasma's memory."""
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
    m = re.search(
        r"(?:remember(?:\s+that)?|don't\s+forget\s+that|note\s+that)\s+(.+)",
        utterance,
        re.IGNORECASE,
    )
    if not m:
        return "What would you like me to remember?"
    fact = m.group(1).strip().rstrip(".?!").strip()

    # Reject clearly incomplete transcripts
    if not fact or len(fact) < 4:
        return "That sounded cut off. Could you repeat the full sentence?"
    if fact.endswith("...") or "..." in fact:
        return "That sounded cut off. Could you repeat the full sentence?"

    _mem().add_fact(category="user_note", content=fact, source="voice_skill")
    return f"Got it. I'll remember: {fact}."


def self_test() -> bool:
    return True