"""Tests for Sprint 6 skills: PA-41 calendar today, PA-42 email count, PA-43 calendar add."""
from __future__ import annotations
from datetime import datetime, timedelta


# ── PA-41 Calendar Today ──────────────────────────────────────────────────────

def test_calendar_self_test():
    from backend.skills.calendar_today import self_test
    assert self_test()

def test_calendar_fmt_time_pm():
    from backend.skills.calendar_today import _fmt_time
    assert _fmt_time("2026-06-02T14:30:00.0000000") == "2:30 PM"

def test_calendar_fmt_time_am():
    from backend.skills.calendar_today import _fmt_time
    assert _fmt_time("2026-06-02T09:00:00.0000000") == "9 AM"

def test_calendar_fmt_time_noon():
    from backend.skills.calendar_today import _fmt_time
    assert _fmt_time("2026-06-02T12:00:00.0000000") == "12 PM"

def test_calendar_fmt_time_midnight():
    from backend.skills.calendar_today import _fmt_time
    assert _fmt_time("2026-06-02T00:00:00.0000000") == "12 AM"

def test_calendar_not_configured():
    from backend.skills.calendar_today import run
    r = run({"utterance": "what's on my calendar"})
    # Should return setup message when MS not configured
    assert "script" in r.lower() or "linked" in r.lower() or "calendar" in r.lower()

def test_calendar_meta_triggers():
    from backend.skills.calendar_today import META
    triggers = META["triggers"]
    assert any("calendar" in t for t in triggers)
    assert any("meeting" in t for t in triggers)


# ── PA-42 Email Count ─────────────────────────────────────────────────────────

def test_email_self_test():
    from backend.skills.email_count import self_test
    assert self_test()

def test_email_not_configured():
    from backend.skills.email_count import run
    r = run({})
    assert "script" in r.lower() or "linked" in r.lower() or "inbox" in r.lower() or "email" in r.lower()

def test_email_meta_triggers():
    from backend.skills.email_count import META
    triggers = META["triggers"]
    assert any("email" in t for t in triggers)
    assert any("inbox" in t for t in triggers)


# ── PA-43 Calendar Add ────────────────────────────────────────────────────────

def test_calendar_add_self_test():
    from backend.skills.calendar_add import self_test
    assert self_test()

def test_calendar_add_parse_3pm():
    from backend.skills.calendar_add import _parse_datetime
    dt = _parse_datetime("schedule a meeting at 3pm tomorrow")
    assert dt is not None
    assert dt.hour == 15

def test_calendar_add_parse_am():
    from backend.skills.calendar_add import _parse_datetime
    dt = _parse_datetime("create an event at 10am")
    assert dt is not None
    assert dt.hour == 10

def test_calendar_add_parse_24h():
    from backend.skills.calendar_add import _parse_datetime
    dt = _parse_datetime("schedule a call at 14:30")
    assert dt is not None
    assert dt.hour == 14
    assert dt.minute == 30

def test_calendar_add_parse_monday():
    from backend.skills.calendar_add import _parse_datetime
    dt = _parse_datetime("book a meeting at 9am on Monday")
    assert dt is not None
    assert dt.hour == 9
    assert dt.weekday() == 0  # Monday

def test_calendar_add_parse_tomorrow():
    from backend.skills.calendar_add import _parse_datetime
    dt = _parse_datetime("meeting at 2pm tomorrow")
    assert dt is not None
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    assert dt.date() == tomorrow

def test_calendar_add_extract_title_simple():
    from backend.skills.calendar_add import _extract_title
    title = _extract_title("schedule a meeting with John at 3pm tomorrow")
    assert "john" in title.lower()

def test_calendar_add_extract_title_call():
    from backend.skills.calendar_add import _extract_title
    title = _extract_title("schedule a call with the team at 10am")
    assert "team" in title.lower() or "call" in title.lower()

def test_calendar_add_extract_title_event():
    from backend.skills.calendar_add import _extract_title
    title = _extract_title("create an event dentist appointment at 11am")
    assert "dentist" in title.lower()

def test_calendar_add_not_configured():
    from backend.skills.calendar_add import run
    r = run({"utterance": "schedule a meeting at 3pm tomorrow"})
    assert "script" in r.lower() or "linked" in r.lower() or "done" in r.lower() or "couldn't" in r.lower()

def test_calendar_add_meta_triggers():
    from backend.skills.calendar_add import META
    triggers = META["triggers"]
    assert any("calendar" in t for t in triggers)
    assert any("meeting" in t for t in triggers)
