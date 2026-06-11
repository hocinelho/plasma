"""Tests for Google Calendar + Gmail integration.

All tests mock the google_client module so they work without credentials
or network access.
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import json


# ── google_client.is_configured ──────────────────────────────────────────────

def test_google_not_configured_when_no_token():
    """is_configured returns False when no token file exists."""
    with patch("backend.core.google_client.TOKEN_PATH") as mock_path:
        mock_path.exists.return_value = False
        from backend.core.google_client import is_configured
        # Reimport to get fresh evaluation
        assert is_configured() is False


def test_google_configured_with_valid_token(tmp_path):
    """is_configured returns True when token file has a refresh_token."""
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({
        "access_token": "ya29.fake",
        "refresh_token": "1//fake-refresh",
        "expiry": 9999999999,
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake-secret",
    }))
    with patch("backend.core.google_client.TOKEN_PATH", token_file):
        from backend.core.google_client import is_configured
        assert is_configured() is True


# ── calendar_today — Google path ─────────────────────────────────────────────

def test_calendar_today_uses_google_when_configured():
    """calendar_today reads from Google Calendar when google_client is configured."""
    mock_events = {
        "items": [
            {
                "summary": "Team standup",
                "start": {"dateTime": "2026-06-11T09:00:00+02:00"},
                "end": {"dateTime": "2026-06-11T09:30:00+02:00"},
            },
            {
                "summary": "Lunch",
                "start": {"date": "2026-06-11"},
                "end": {"date": "2026-06-11"},
            },
        ]
    }

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value=mock_events):
        from backend.skills.calendar_today import run
        result = run({})
        assert "Team standup" in result
        assert "Lunch" in result
        assert "2 events" in result


def test_calendar_today_single_google_event():
    """calendar_today handles a single Google event properly."""
    mock_events = {
        "items": [
            {
                "summary": "Dentist",
                "start": {"dateTime": "2026-06-11T14:30:00+02:00"},
                "end": {"dateTime": "2026-06-11T15:00:00+02:00"},
            },
        ]
    }

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value=mock_events):
        from backend.skills.calendar_today import run
        result = run({})
        assert "one meeting" in result.lower()
        assert "Dentist" in result


def test_calendar_today_no_google_events():
    """calendar_today reports empty calendar."""
    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value={"items": []}):
        from backend.skills.calendar_today import run
        result = run({})
        assert "nothing" in result.lower()


# ── email_count — Gmail path ─────────────────────────────────────────────────

def test_email_count_uses_gmail_labels():
    """email_count uses the Gmail Labels endpoint for unread count."""
    mock_label = {
        "id": "INBOX",
        "name": "INBOX",
        "messagesTotal": 150,
        "messagesUnread": 7,
        "threadsTotal": 100,
        "threadsUnread": 5,
    }

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value=mock_label):
        from backend.skills.email_count import run
        result = run({})
        assert "7" in result
        assert "unread" in result.lower()


def test_email_count_zero_unread():
    """email_count reports clear inbox with 0 unread."""
    mock_label = {"messagesUnread": 0}

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value=mock_label):
        from backend.skills.email_count import run
        result = run({})
        assert "clear" in result.lower() or "no unread" in result.lower()


def test_email_count_one_unread():
    """email_count reports singular when count is 1."""
    mock_label = {"messagesUnread": 1}

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_get", return_value=mock_label):
        from backend.skills.email_count import run
        result = run({})
        assert "1 unread email" in result


# ── calendar_add — Google path ───────────────────────────────────────────────

def test_calendar_add_uses_google_when_configured():
    """calendar_add creates an event via Google Calendar API."""
    mock_response = {"id": "abc123", "status": "confirmed"}

    with patch("backend.core.google_client.is_configured", return_value=True), \
         patch("backend.core.google_client.google_post", return_value=mock_response) as mock_post:
        from backend.skills.calendar_add import run
        result = run({"utterance": "schedule a meeting with Alice at 3pm tomorrow"})
        assert "done" in result.lower() or "added" in result.lower()
        # Verify the Google Calendar endpoint was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "calendars/primary/events" in call_args[0][0]
        body = call_args[0][1]
        assert "summary" in body
        assert "start" in body
        assert "end" in body


# ── Fallback behavior ────────────────────────────────────────────────────────

def test_calendar_today_fallback_to_ms_graph():
    """When Google is not configured, calendar_today falls back to MS Graph."""
    with patch("backend.core.google_client.is_configured", return_value=False), \
         patch("backend.core.ms_graph.is_configured", return_value=False):
        from backend.skills.calendar_today import run
        result = run({})
        assert "google_auth" in result.lower() or "ms_auth" in result.lower() or "linked" in result.lower()


def test_email_count_fallback_to_ms_graph():
    """When Google is not configured, email_count falls back to MS Graph."""
    with patch("backend.core.google_client.is_configured", return_value=False), \
         patch("backend.core.ms_graph.is_configured", return_value=False):
        from backend.skills.email_count import run
        result = run({})
        assert "google_auth" in result.lower() or "ms_auth" in result.lower() or "linked" in result.lower()


def test_calendar_add_fallback_not_linked():
    """When neither provider configured, calendar_add returns setup instructions."""
    with patch("backend.core.google_client.is_configured", return_value=False), \
         patch("backend.core.ms_graph.is_configured", return_value=False):
        from backend.skills.calendar_add import run
        result = run({"utterance": "schedule a meeting at 3pm tomorrow"})
        assert "google_auth" in result.lower() or "ms_auth" in result.lower() or "linked" in result.lower()


def test_calendar_today_ms_graph_fallback_works():
    """When Google not configured but MS Graph is, uses MS Graph."""
    mock_ms_data = {
        "value": [
            {
                "subject": "Board meeting",
                "start": {"dateTime": "2026-06-11T10:00:00.0000000"},
                "end": {"dateTime": "2026-06-11T11:00:00.0000000"},
                "isAllDay": False,
            }
        ]
    }

    with patch("backend.core.google_client.is_configured", return_value=False), \
         patch("backend.core.ms_graph.is_configured", return_value=True), \
         patch("backend.core.ms_graph.graph_get", return_value=mock_ms_data):
        from backend.skills.calendar_today import run
        result = run({})
        assert "Board meeting" in result


# ── META descriptions updated ────────────────────────────────────────────────

def test_calendar_today_meta_mentions_google():
    """calendar_today META description mentions Google Calendar."""
    from backend.skills.calendar_today import META
    assert "google" in META["description"].lower() or "Google" in META["description"]


def test_calendar_add_meta_mentions_google():
    """calendar_add META description mentions Google Calendar."""
    from backend.skills.calendar_add import META
    assert "google" in META["description"].lower() or "Google" in META["description"]


def test_email_count_meta_mentions_gmail():
    """email_count META description mentions Gmail."""
    from backend.skills.email_count import META
    assert "gmail" in META["description"].lower() or "Gmail" in META["description"]
