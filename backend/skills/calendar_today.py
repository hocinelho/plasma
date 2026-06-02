"""PA-41 — Calendar today: "what's on my calendar today" / "any meetings today"."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

META = {
    "name": "calendar_today",
    "description": "Reads today's Outlook calendar events via Microsoft Graph.",
    "triggers": [
        "what's on my calendar",
        "what is on my calendar",
        "my calendar today",
        "calendar today",
        "my schedule today",
        "what meetings do i have",
        "any meetings today",
        "any appointments today",
        "what appointments",
        "my schedule",
    ],
}

_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _fmt_time(iso: str) -> str:
    """'2026-06-02T14:30:00.0000000' → '2:30 PM'"""
    try:
        dt = datetime.fromisoformat(iso.split(".")[0])
        hour, minute = dt.hour, dt.minute
        period = "AM" if hour < 12 else "PM"
        h = hour % 12 or 12
        return f"{h}:{minute:02d} {period}" if minute else f"{h} {period}"
    except Exception:
        return iso[:5]


def run(args: dict | None = None) -> str:
    try:
        from backend.core.ms_graph import graph_get, is_configured
    except ImportError:
        return "Microsoft Graph is not available."

    if not is_configured():
        return "Outlook isn't linked yet. Run: python scripts/ms_auth.py"

    try:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        fmt = "%Y-%m-%dT%H:%M:%S"
        data = graph_get(
            "calendarView",
            startDateTime=start.strftime(fmt),
            endDateTime=end.strftime(fmt),
            **{"$select": "subject,start,end,isAllDay", "$orderby": "start/dateTime", "$top": "10"},
        )

        events = data.get("value", [])
        if not events:
            return "You have nothing on your calendar today."

        if len(events) == 1:
            e = events[0]
            if e.get("isAllDay"):
                return f"You have one all-day event today: {e['subject']}."
            t = _fmt_time(e["start"]["dateTime"])
            return f"You have one meeting today: {e['subject']} at {t}."

        parts = []
        for e in events[:5]:
            if e.get("isAllDay"):
                parts.append(f"{e['subject']} (all day)")
            else:
                t = _fmt_time(e["start"]["dateTime"])
                parts.append(f"{e['subject']} at {t}")

        count = len(events)
        listed = ", ".join(parts[:-1]) + f", and {parts[-1]}"
        return f"You have {count} events today: {listed}."

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't read your calendar: {e}"


def self_test() -> bool:
    # Offline-safe: just verify the module imports and _fmt_time works
    assert _fmt_time("2026-06-02T14:30:00.0000000") == "2:30 PM"
    assert _fmt_time("2026-06-02T09:00:00.0000000") == "9 AM"
    return True
