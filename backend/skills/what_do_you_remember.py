"""Reads back stored facts."""
from backend.modules.memory.store import MemoryStore

META = {
    "name": "what_do_you_remember",
    "description": "Summarizes stored facts about the user.",
    "triggers": ["what do you remember", "what do you know about me", "recall facts"],
}

_memory = None
def _mem():
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory

def run(args=None):
    facts = _mem().get_facts(limit=10)
    if not facts:
        return "I don't have any facts stored about you yet."
    bullets = [f["content"] for f in facts]
    return "Here's what I remember: " + "; ".join(bullets) + "."

def self_test():
    return True