"""
Skill: get_time — returns the current local time.

A skill is a Python file with a `run(args: dict) -> str` function and a
`META` dict describing triggers + description. The skill registry auto-loads
every `*.py` file under .plasma/skills/ that exposes these.
"""
from __future__ import annotations
from datetime import datetime


META = {
    "name": "get_time",
    "description": "Returns the current local time.",
    "triggers": [
        "what time",
        "what's the time",
        "current time",
        "time is it",
        "tell me the time",
    ],
    "example_utterances": [
        "What time is it?",
        "Plasma, tell me the time",
        "What's the time now?",
    ],
}


def run(args: dict | None = None) -> str:
    """Return a natural-language statement of the current local time."""
    now = datetime.now()
    return f"It's {now.strftime('%H:%M')}."


def self_test() -> bool:
    """Return True if the skill works. Called by registry on load."""
    result = run({})
    return (
        isinstance(result, str)
        and result.startswith("It's ")
        and len(result) >= 8
    )