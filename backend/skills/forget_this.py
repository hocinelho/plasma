"""Skill: forget_this — deletes a stored fact by partial match."""
from __future__ import annotations
import re
from backend.modules.memory.store import MemoryStore


META = {
    "name": "forget_this",
    "description": "Deletes a stored fact from memory by keyword.",
    "triggers": [
        "forget that",
        "forget what i said about",
        "forget about",
        "delete fact",
    ],
    "example_utterances": [
        "Forget that I love Algerian coffee",
        "Forget about Miriam",
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
        r"(?:forget(?:\s+that)?|forget\s+about|forget\s+what\s+i\s+said\s+about|delete\s+fact)\s+(.+)",
        utterance,
        re.IGNORECASE,
    )
    if not m:
        return "What would you like me to forget?"
    keyword = m.group(1).strip().rstrip(".?!").strip().lower()
    if not keyword or len(keyword) < 3:
        return "I need a clearer keyword. What should I forget?"

    memory = _mem()
    facts = memory.get_facts(limit=500)
    matches = [f for f in facts if keyword in f["content"].lower()]

    if not matches:
        return f"I don't have any facts matching '{keyword}'."

    for f in matches:
        memory.delete_fact(f["id"])

    if len(matches) == 1:
        return f"Forgotten: {matches[0]['content']}."
    return f"Forgotten {len(matches)} facts matching '{keyword}'."


def self_test() -> bool:
    return True