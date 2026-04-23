"""Temporary smoke test for all loaded skills — delete after verifying."""
from backend.modules.skills.registry import get_registry

r = get_registry()
print("Skills loaded:", [s.name for s in r.list()])
print()

tests = [
    "what time is it?",
    "what's the date today?",
    "open notepad",
    "remember that I love strong coffee",
    "what do you remember about me?",
    "tell me a joke",  # should NOT match any skill
]

for t in tests:
    skill = r.find_by_trigger(t)
    if skill:
        print(f"  {t!r:50s} -> {skill.name}")
    else:
        print(f"  {t!r:50s} -> (no match, would fall through to LLM)")