"""PA-43 — Add to calendar: "schedule a meeting with John at 3pm tomorrow"."""
from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

META = {
    "name": "calendar_add",
    "description": "Creates a new Outlook calendar event by voice.",
    "triggers": [
        "add to my calendar",
        "add to calendar",
        "schedule a meeting",
        "schedule a call",
        "create a meeting",
        "create an event",
        "book a meeting",
        "put on my calendar",
        "set up a meeting",
    ],
}

# Relative day words
_DAY_OFFSETS = {
    "today": 0, "tonight": 0,
    "tomorrow": 1,
    "monday": None, "tuesday": None, "wednesday": None,
    "thursday": None, "friday": None, "saturday": None, "sunday": None,
}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# "at 3pm", "at 14:30", "at 3:30 pm"
_TIME_RE = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.I,
)
_DAY_RE = re.compile(
    r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
# Strip leading skill triggers to get the event title
_TITLE_STRIP = re.compile(
    r"^(?:add\s+(?:to\s+(?:my\s+)?calendar)?|schedule\s+a?\s*|create\s+an?\s*(?:event|meeting)?|"
    r"book\s+a?\s*(?:meeting)?|put\s+on\s+my\s+calendar|set\s+up\s+a?\s*(?:meeting)?)\s*",
    re.I,
)
# Remove "at <time>" and day words from title
_AT_TIME_STRIP = re.compile(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b.*$", re.I)
_DAY_SUFFIX_STRIP = re.compile(
    r"\s+(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
    re.I,
)


def _parse_datetime(utterance: str) -> datetime | None:
    """Extract a datetime from the utterance. Returns None if unparseable."""
    now = datetime.now()

    # Find time
    tm = _TIME_RE.search(utterance)
    hour = 12  # default: noon
    minute = 0
    if tm:
        hour = int(tm.group(1))
        minute = int(tm.group(2) or 0)
        ampm = (tm.group(3) or "").lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif not ampm and hour < 7:
            hour += 12  # "at 3" without am/pm → assume PM

    # Find day
    dm = _DAY_RE.search(utterance)
    if dm:
        day_word = dm.group(1).lower()
        offset = _DAY_OFFSETS.get(day_word)
        if offset is not None:
            target = now + timedelta(days=offset)
        else:
            # Weekday name → find next occurrence
            target_wd = _WEEKDAYS.index(day_word)
            days_ahead = (target_wd - now.weekday()) % 7 or 7
            target = now + timedelta(days=days_ahead)
    else:
        # No day mentioned → assume today, or tomorrow if time already passed
        target = now
        if now.replace(hour=hour, minute=minute, second=0, microsecond=0) <= now:
            target = now + timedelta(days=1)

    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _extract_title(utterance: str) -> str:
    title = _TITLE_STRIP.sub("", utterance).strip()
    title = _AT_TIME_STRIP.sub("", title).strip()
    title = _DAY_SUFFIX_STRIP.sub("", title).strip(" .?")
    return title or "New Event"


def run(args: dict | None = None) -> str:
    try:
        from backend.core.ms_graph import graph_post, is_configured
    except ImportError:
        return "Microsoft Graph is not available."

    if not is_configured():
        return "Outlook isn't linked yet. Run: python scripts/ms_auth.py"

    utterance = (args or {}).get("utterance", "")
    title = _extract_title(utterance)
    dt = _parse_datetime(utterance)

    if dt is None:
        return "I couldn't parse the time. Try: 'schedule a meeting with John at 3pm tomorrow'."

    start_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = (dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    try:
        graph_post("events", {
            "subject": title,
            "start": {"dateTime": start_iso, "timeZone": "Europe/Berlin"},
            "end": {"dateTime": end_iso, "timeZone": "Europe/Berlin"},
        })
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        day_str = dt.strftime("%A")
        return f"Done. '{title}' added to your calendar for {day_str} at {time_str}."
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't create the event: {e}"


def self_test() -> bool:
    # Offline-safe: test parsing logic only
    dt = _parse_datetime("schedule a meeting at 3pm tomorrow")
    assert dt is not None and dt.hour == 15
    title = _extract_title("schedule a meeting with John at 3pm tomorrow")
    assert "john" in title.lower() or "meeting" in title.lower()
    return True
