"""PA-79 — Teams: "what's my next Teams meeting" / meeting summary by voice.

Reuses the existing Microsoft Graph app (PA-41/42/43) — no new app
registration or consent needed, since Teams meetings show up as regular
calendar events with isOnlineMeeting=true via the Calendars.Read scope
already requested.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

META = {
    "name": "teams_summary",
    "description": "Summarizes your next Microsoft Teams meeting today.",
    "triggers": [
        "next teams meeting",
        "teams meeting",
        "teams summary",
        "my teams meetings",
        "any teams meetings",
        "teams agenda",
        "nächstes teams meeting",
        "teams besprechung",
        "teams zusammenfassung",
        "meine teams meetings",
    ],
}


def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.split(".")[0])
        hour, minute = dt.hour, dt.minute
        period = "AM" if hour < 12 else "PM"
        h = hour % 12 or 12
        return f"{h}:{minute:02d} {period}" if minute else f"{h} {period}"
    except Exception:
        return iso[:5]


def _summarize(events: list[dict]) -> str:
    if not events:
        return "You have no Teams meetings today."

    next_event = events[0]
    subject = next_event.get("subject", "(No title)")
    start = _fmt_time(next_event.get("start", {}).get("dateTime", ""))
    attendees = next_event.get("attendees", [])
    n_attendees = len(attendees)

    parts = [f"Your next Teams meeting is '{subject}' at {start}"]
    if n_attendees:
        parts.append(f"with {n_attendees} attendee{'s' if n_attendees != 1 else ''}")
    summary = " ".join(parts) + "."

    remaining = len(events) - 1
    if remaining > 0:
        summary += f" You have {remaining} more Teams meeting{'s' if remaining != 1 else ''} today."
    return summary


def _read_teams_meetings() -> str:
    from backend.core.ms_graph import graph_get

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    fmt = "%Y-%m-%dT%H:%M:%S"
    data = graph_get(
        "calendarView",
        startDateTime=start.strftime(fmt),
        endDateTime=end.strftime(fmt),
        **{
            "$select": "subject,start,end,isOnlineMeeting,onlineMeetingProvider,attendees",
            "$orderby": "start/dateTime",
            "$top": "20",
        },
    )

    raw_events = data.get("value", [])
    teams_events = [
        e for e in raw_events
        if e.get("isOnlineMeeting") and e.get("onlineMeetingProvider") == "teamsForBusiness"
    ]
    return _summarize(teams_events)


def run(args: dict | None = None) -> str:
    try:
        from backend.core.ms_graph import is_configured as ms_configured
        if not ms_configured():
            return "No Microsoft account linked yet. Run: python scripts/ms_auth.py"
        return _read_teams_meetings()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't read your Teams meetings: {e}"


def self_test() -> bool:
    assert _fmt_time("2026-06-02T14:30:00.0000000") == "2:30 PM"
    assert _summarize([]) == "You have no Teams meetings today."
    one = [{"subject": "Standup", "start": {"dateTime": "2026-06-02T09:00:00.0000000"}, "attendees": [{}, {}]}]
    out = _summarize(one)
    assert "Standup" in out and "9 AM" in out and "2 attendees" in out
    return True
