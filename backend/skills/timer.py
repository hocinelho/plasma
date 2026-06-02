"""PA-53 — Timer skill: "set a timer for 5 minutes"."""
from __future__ import annotations
import re
import threading
import time

META = {
    "name": "timer",
    "description": "Sets a countdown timer and notifies when done.",
    "triggers": [
        "set a timer",
        "timer for",
        "set timer",
        "countdown for",
        "remind me in",
        "alert me in",
    ],
}

_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}

_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)",
    re.IGNORECASE,
)


def _parse_seconds(text: str) -> int | None:
    total = 0
    found = False
    for m in _PATTERN.finditer(text):
        value = float(m.group(1))
        unit = m.group(2).lower()
        total += int(value * _UNITS[unit])
        found = True
    return total if found else None


def _ring(label: str) -> None:
    print(f"\n*** PLASMA TIMER: {label} ***\n", flush=True)


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")
    seconds = _parse_seconds(utterance)

    if not seconds:
        return "How long should I set the timer for? Say something like 'set a timer for 5 minutes'."

    if seconds > 86400:
        return "I can only set timers up to 24 hours."

    if seconds >= 3600:
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        label = f"{h}h {m}m" if m else f"{h} hour{'s' if h > 1 else ''}"
    elif seconds >= 60:
        m = seconds // 60
        s = seconds % 60
        label = f"{m}m {s}s" if s else f"{m} minute{'s' if m > 1 else ''}"
    else:
        label = f"{seconds} second{'s' if seconds != 1 else ''}"

    threading.Thread(
        target=lambda: (time.sleep(seconds), _ring(label)),
        daemon=True,
    ).start()

    return f"Timer set for {label}."


def self_test() -> bool:
    result = run({"utterance": "set a timer for 30 seconds"})
    return "30 second" in result
