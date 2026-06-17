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
        "ما التاريخ",
        "ما هو اليوم",
        "اليوم كم",
        "ما هو تاريخ اليوم",
        "ما اليوم",
    ],
}

_DE_DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_DE_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

_AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
_AR_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]


def run(args=None) -> str:
    now = datetime.now()
    language = (args or {}).get("language", "en")
    if language == "de":
        day = _DE_DAYS[now.weekday()]
        month = _DE_MONTHS[now.month - 1]
        return f"Heute ist {day}, der {now.day}. {month} {now.year}."
    if language == "ar":
        day = _AR_DAYS[now.weekday()]
        month = _AR_MONTHS[now.month - 1]
        return f"اليوم هو {day}، {now.day} {month} {now.year}."
    return now.strftime("Today is %A, %B %d, %Y.")


def self_test() -> bool:
    return "Today is" in run()
