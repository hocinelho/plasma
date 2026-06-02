"""PA-59 — Reminder skill: "remind me at 3pm to take medication" / "remind me in 10 minutes to call Bob"."""
from __future__ import annotations
import re
import threading
import time
from datetime import datetime, timedelta

META = {
    "name": "reminder",
    "description": "Sets a reminder for a specific time or after a delay.",
    "triggers": [
        "remind me ",
        "reminder ",
        "set a reminder",
        "don't let me forget",
        "alert me ",
        "notify me ",
    ],
}

# "remind me in X minutes/hours/seconds to <message>"
_RELATIVE = re.compile(
    r"(?:remind\s+me|alert\s+me|notify\s+me)\s+in\s+"
    r"(?:(\d+)\s*hours?\s*)?(?:(\d+)\s*minutes?\s*)?(?:(\d+)\s*seconds?)?"
    r"\s+(?:to|about|that)\s+(.+)",
    re.I,
)

# "remind me at 3pm / 15:30 to <message>"
_ABSOLUTE = re.compile(
    r"(?:remind\s+me|alert\s+me|notify\s+me)\s+at\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
    r"\s+(?:to|about|that)\s+(.+)",
    re.I,
)


def _fire(delay_s: float, message: str) -> None:
    time.sleep(delay_s)
    # In a real app this would trigger TTS or a system notification.
    # For now print to server console — sufficient for voice assistant demo.
    print(f"\n🔔 REMINDER: {message}\n", flush=True)


def _schedule(delay_s: float, message: str) -> None:
    t = threading.Thread(target=_fire, args=(delay_s, message), daemon=True)
    t.start()


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")

    # Try relative time first
    m = _RELATIVE.search(utterance)
    if m:
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)
        message = m.group(4).strip(" ?.")
        total_s = hours * 3600 + minutes * 60 + seconds

        if total_s <= 0:
            return "I didn't catch how long to wait. Try 'remind me in 10 minutes to call Bob'."

        _schedule(total_s, message)

        parts = []
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        return f"I'll remind you to {message} in {', '.join(parts)}."

    # Try absolute time
    m = _ABSOLUTE.search(utterance)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower()
        message = m.group(4).strip(" ?.")

        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        delay_s = (target - now).total_seconds()
        _schedule(delay_s, message)

        time_str = target.strftime("%I:%M %p").lstrip("0")
        return f"I'll remind you to {message} at {time_str}."

    return "Try: 'remind me in 10 minutes to call Bob' or 'remind me at 3pm to take medication'."


def self_test() -> bool:
    r = run({"utterance": "remind me in 1 minute to take a break"})
    return "remind" in r.lower() and "1 minute" in r
