"""Returns the current local time — English and German."""
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
        "wie spät ist es",
        "wie viel uhr",
        "wieviel uhr",
        "uhrzeit",
        "wie spät",
    ],
    "example_utterances": [
        "What time is it?",
        "Wie spät ist es?",
    ],
}


def run(args: dict | None = None) -> str:
    now = datetime.now()
    language = (args or {}).get("language", "en")
    if language == "de":
        return f"Es ist {now.strftime('%H:%M')} Uhr."
    return f"It's {now.strftime('%H:%M')}."


def self_test() -> bool:
    r = run({})
    return isinstance(r, str) and r.startswith("It's") and len(r) >= 8
