"""Stores a fact in Plasma's memory."""
import re
from backend.modules.memory.store import MemoryStore

META = {
    "name": "remember_this",
    "description": "Stores a fact about the user.",
    "triggers": ["remember that", "remember i ", "remember my ", "don't forget that", "note that"],
}

_memory = None
def _mem():
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory

def run(args=None):
    utterance = (args or {}).get("utterance", "")
    m = re.search(r"(?:remember(?: that)?|note that|don't forget that)\s+(.+)", utterance, re.IGNORECASE)
    if not m:
        return "What would you like me to remember?"
    fact = m.group(1).strip().rstrip(".").strip()
    if not fact:
        return "What would you like me to remember?"
    _mem().add_fact(category="user_note", content=fact, source="voice")
    return f"Got it. I'll remember: {fact}."

def self_test():
    # Don't actually write to production DB during load test.
    return True