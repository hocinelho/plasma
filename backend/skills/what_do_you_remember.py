"""Skill: what_do_you_remember — reads stored facts back in second person."""
from __future__ import annotations
import re
from backend.modules.memory.store import MemoryStore


META = {
    "name": "what_do_you_remember",
    "description": "Reads back stored facts about the user.",
    "triggers": [
        "what do you remember",
        "what do you know about me",
        "recall facts",
        "what have i told you",
    ],
    "example_utterances": [
        "What do you remember about me?",
        "What do you know about me?",
    ],
}

_memory: MemoryStore | None = None


def _mem() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


# Tiny first-person → second-person rewriter.
# Doesn't have to be perfect; we just want "I love X" -> "You love X".
_FIRST_TO_SECOND: list[tuple[str, str]] = [
    (r"\bI am\b",     "You are"),
    (r"\bI'm\b",      "You're"),
    (r"\bI have\b",   "You have"),
    (r"\bI've\b",     "You've"),
    (r"\bI had\b",    "You had"),
    (r"\bI was\b",    "You were"),
    (r"\bI will\b",   "You will"),
    (r"\bI'll\b",     "You'll"),
    (r"\bI do\b",     "You do"),
    (r"\bI don't\b",  "You don't"),
    (r"\bI can\b",    "You can"),
    (r"\bI can't\b",  "You can't"),
    (r"\bI like\b",   "You like"),
    (r"\bI love\b",   "You love"),
    (r"\bI hate\b",   "You hate"),
    (r"\bI want\b",   "You want"),
    (r"\bI need\b",   "You need"),
    (r"\bI live\b",   "You live"),
    (r"\bI work\b",   "You work"),
    (r"\bI prefer\b", "You prefer"),
    (r"\bI\b",        "You"),
    (r"\bmy\b",       "your"),
    (r"\bMy\b",       "Your"),
    (r"\bmine\b",     "yours"),
    (r"\bmyself\b",   "yourself"),
    (r"\bme\b",       "you"),
]


def _rewrite(fact: str) -> str:
    out = fact.strip()
    for pattern, repl in _FIRST_TO_SECOND:
        out = re.sub(pattern, repl, out)
    return out


def run(args: dict | None = None) -> str:
    facts = _mem().get_facts(limit=10)
    if not facts:
        return "I don't have any facts stored about you yet."
    rewritten = [_rewrite(f["content"]).rstrip(". ") for f in facts]
    return "Here's what I know: " + "; ".join(rewritten) + "."


def self_test() -> bool:
    assert _rewrite("I love Algerian coffee") == "You love Algerian coffee"
    assert _rewrite("my son's name is Malik").startswith("your ")
    return True