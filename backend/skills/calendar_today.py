"""PA-41 — Calendar today: "what's on my calendar today" / "any meetings today"."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

META = {
    "name": "calendar_today",
    "description": "Reads today's Google Calendar / Outlook calendar events.",
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


def _format_events(events: list[dict], source: str = "outlook") -> str:
    """Format a list of normalized events into a spoken response."""
    if not events:
        return "You have nothing on your calendar today."

    if len(events) == 1:
        e = events[0]
        if e.get("is_all_day"):
            return f"You have one all-day event today: {e['subject']}."
        t = _fmt_time(e["start_time"])
        return f"You have one meeting today: {e['subject']} at {t}."

    parts = []
    for e in events[:5]:
        if e.get("is_all_day"):
            parts.append(f"{e['subject']} (all day)")
        else:
            t = _fmt_time(e["start_time"])
            parts.append(f"{e['subject']} at {t}")

    count = len(events)
    listed = ", ".join(parts[:-1]) + f", and {parts[-1]}"
    return f"You have {count} events today: {listed}."


def _read_google_calendar() -> str:
    """Read today's events from Google Calendar."""
    from backend.core.google_client import google_get

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    data = google_get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        timeMin=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        timeMax=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        singleEvents="true",
        orderBy="startTime",
        maxResults="10",
    )

    raw_events = data.get("items", [])
    events = []
    for e in raw_events:
        start_info = e.get("start", {})
        is_all_day = "date" in start_info and "dateTime" not in start_info
        start_time = start_info.get("dateTime", start_info.get("date", ""))
        events.append({
            "subject": e.get("summary", "(No title)"),
            "start_time": start_time,
            "is_all_day": is_all_day,
        })

    return _format_events(events, source="google")


def _read_ms_calendar() -> str:
    """Read today's events from Outlook via MS Graph."""
    from backend.core.ms_graph import graph_get

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

    raw_events = data.get("value", [])
    events = []
    for e in raw_events:
        events.append({
            "subject": e.get("subject", "(No title)"),
            "start_time": e.get("start", {}).get("dateTime", ""),
            "is_all_day": e.get("isAllDay", False),
        })

    return _format_events(events, source="outlook")


def run(args: dict | None = None) -> str:
    # Try Google Calendar first
    try:
        from backend.core.google_client import is_configured as google_configured
        if google_configured():
            try:
                return _read_google_calendar()
            except Exception as e:
                return f"Couldn't read your Google Calendar: {e}"
    except ImportError:
        pass

    # Fall back to Microsoft Graph
    try:
        from backend.core.ms_graph import is_configured as ms_configured
        if ms_configured():
            try:
                return _read_ms_calendar()
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"Couldn't read your calendar: {e}"
    except ImportError:
        pass

    return (
        "No calendar linked yet. Run:\n"
        "  python scripts/google_auth.py   (Google Calendar)\n"
        "  python scripts/ms_auth.py       (Outlook)"
    )


def self_test() -> bool:
    # Offline-safe: just verify the module imports and _fmt_time works
    assert _fmt_time("2026-06-02T14:30:00.0000000") == "2:30 PM"
    assert _fmt_time("2026-06-02T09:00:00.0000000") == "9 AM"
    return True
