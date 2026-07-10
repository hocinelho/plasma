"""Returns today's date — English and German."""
from __future__ import annotations
from datetime import datetime

META = {
    "name": "get_date",
    "description": "Returns today's date.",
    "triggers": [
        "what's the date",
        "what date",
        "today's date",
        "what day is it",
        "welches datum",
        "welcher tag ist heute",
        "was für ein tag",
        "was ist heute für ein datum",
        "heutiges datum",
    ],
}

_DE_DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_DE_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

def run(args=None) -> str:
    now = datetime.now()
    language = (args or {}).get("language", "en")
    if language == "de":
        day = _DE_DAYS[now.weekday()]
        month = _DE_MONTHS[now.month - 1]
        return f"Heute ist {day}, der {now.day}. {month} {now.year}."
    return now.strftime("Today is %A, %B %d, %Y.")


def self_test() -> bool:
    return "Today is" in run()
