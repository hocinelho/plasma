"""Tests for S13 — Slack (PA-78), Teams (PA-79), WhatsApp (PA-80).

All tests mock the respective client modules so they work without
credentials or network access.
"""
from __future__ import annotations
from unittest.mock import patch


# ── slack_client.is_configured ───────────────────────────────────────────────

def test_slack_not_configured_when_no_token():
    with patch("backend.core.config.config.SLACK_USER_TOKEN", ""):
        from backend.core.slack_client import is_configured
        assert is_configured() is False


def test_slack_configured_with_token():
    with patch("backend.core.config.config.SLACK_USER_TOKEN", "xoxp-fake"):
        from backend.core.slack_client import is_configured
        assert is_configured() is True


# ── slack_read skill ──────────────────────────────────────────────────────────

def test_slack_read_extract_channel_explicit():
    from backend.skills.slack_read import _extract_channel
    assert _extract_channel("what's the latest in slack in #engineering") == "engineering"
    assert _extract_channel("check slack in the marketing channel") == "marketing"


def test_slack_read_extract_channel_default():
    from backend.skills.slack_read import _extract_channel, _DEFAULT_CHANNEL
    assert _extract_channel("check slack") == _DEFAULT_CHANNEL


def test_slack_read_not_configured():
    with patch("backend.core.slack_client.is_configured", return_value=False):
        from backend.skills.slack_read import run
        result = run({"utterance": "check slack"})
        assert "slack_user_token" in result.lower() or "not linked" in result.lower() or "isn't linked" in result.lower()


def test_slack_read_latest_message():
    channels = {"ok": True, "channels": [{"id": "C123", "name": "general"}]}
    history = {"ok": True, "messages": [{"text": "Deploy is done", "user": "U1"}]}
    user_info = {"ok": True, "user": {"real_name": "Alice"}}

    def fake_slack_get(method, **params):
        if method == "conversations.list":
            return channels
        if method == "conversations.history":
            return history
        if method == "users.info":
            return user_info
        raise AssertionError(f"unexpected method {method}")

    with patch("backend.core.slack_client.is_configured", return_value=True), \
         patch("backend.core.slack_client.slack_get", side_effect=fake_slack_get):
        from backend.skills.slack_read import run
        result = run({"utterance": "what's the latest in slack"})
        assert "Alice" in result
        assert "Deploy is done" in result
        assert "general" in result


def test_slack_read_unknown_channel():
    with patch("backend.core.slack_client.is_configured", return_value=True), \
         patch("backend.core.slack_client.slack_get", return_value={"ok": True, "channels": []}):
        from backend.skills.slack_read import run
        result = run({"utterance": "check slack in #nonexistent"})
        assert "nonexistent" in result.lower()


def test_slack_read_self_test():
    from backend.skills.slack_read import self_test
    assert self_test()


# ── teams_summary skill ───────────────────────────────────────────────────────

def test_teams_summary_no_meetings():
    with patch("backend.core.ms_graph.is_configured", return_value=True), \
         patch("backend.core.ms_graph.graph_get", return_value={"value": []}):
        from backend.skills.teams_summary import run
        result = run({})
        assert "no teams meetings" in result.lower()


def test_teams_summary_filters_non_teams_events():
    events = {
        "value": [
            {"subject": "Regular event", "start": {"dateTime": "2026-06-11T09:00:00.0000000"},
             "isOnlineMeeting": False, "attendees": []},
            {"subject": "Zoom call", "start": {"dateTime": "2026-06-11T10:00:00.0000000"},
             "isOnlineMeeting": True, "onlineMeetingProvider": "zoomBusiness", "attendees": []},
        ]
    }
    with patch("backend.core.ms_graph.is_configured", return_value=True), \
         patch("backend.core.ms_graph.graph_get", return_value=events):
        from backend.skills.teams_summary import run
        result = run({})
        assert "no teams meetings" in result.lower()


def test_teams_summary_next_meeting():
    events = {
        "value": [
            {
                "subject": "Sprint planning",
                "start": {"dateTime": "2026-06-11T09:00:00.0000000"},
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "teamsForBusiness",
                "attendees": [{}, {}, {}],
            },
        ]
    }
    with patch("backend.core.ms_graph.is_configured", return_value=True), \
         patch("backend.core.ms_graph.graph_get", return_value=events):
        from backend.skills.teams_summary import run
        result = run({})
        assert "Sprint planning" in result
        assert "3 attendees" in result


def test_teams_summary_not_configured():
    with patch("backend.core.ms_graph.is_configured", return_value=False):
        from backend.skills.teams_summary import run
        result = run({})
        assert "ms_auth.py" in result


def test_teams_summary_self_test():
    from backend.skills.teams_summary import self_test
    assert self_test()


# ── twilio_client.is_configured ──────────────────────────────────────────────

def test_twilio_not_configured_when_missing_fields():
    with patch("backend.core.config.config.TWILIO_ACCOUNT_SID", ""), \
         patch("backend.core.config.config.TWILIO_AUTH_TOKEN", ""), \
         patch("backend.core.config.config.TWILIO_WHATSAPP_FROM", ""):
        from backend.core.twilio_client import is_configured
        assert is_configured() is False


def test_twilio_configured_with_all_fields():
    with patch("backend.core.config.config.TWILIO_ACCOUNT_SID", "ACfake"), \
         patch("backend.core.config.config.TWILIO_AUTH_TOKEN", "tokenfake"), \
         patch("backend.core.config.config.TWILIO_WHATSAPP_FROM", "+14155238886"):
        from backend.core.twilio_client import is_configured
        assert is_configured() is True


# ── whatsapp_send skill ────────────────────────────────────────────────────────

def test_whatsapp_parse_recipient_and_message():
    from backend.skills.whatsapp_send import _parse
    assert _parse("send whatsapp to John: running 10 minutes late") == ("John", "running 10 minutes late")
    assert _parse("schreib eine whatsapp an Maria: bin gleich da") == ("Maria", "bin gleich da")


def test_whatsapp_parse_unparseable():
    from backend.skills.whatsapp_send import _parse
    assert _parse("send whatsapp") is None


def test_whatsapp_normalize_phone():
    from backend.skills.whatsapp_send import _normalize_phone
    assert _normalize_phone("+49 170 1234567") == "+491701234567"
    assert _normalize_phone("491701234567") == "+491701234567"


def test_whatsapp_send_with_direct_phone_number():
    with patch("backend.core.twilio_client.send_whatsapp_message", return_value={"sid": "SM123"}) as mock_send:
        from backend.skills.whatsapp_send import run
        result = run({"utterance": "send whatsapp to +491701234567: on my way"})
        assert "Sent" in result
        mock_send.assert_called_once_with("+491701234567", "on my way")


def test_whatsapp_send_resolves_contact_from_memory():
    fake_facts = [{"content": "John's number is +491701234567"}]
    with patch("backend.modules.memory.store.MemoryStore.search_facts", return_value=fake_facts), \
         patch("backend.core.twilio_client.send_whatsapp_message", return_value={"sid": "SM123"}) as mock_send:
        from backend.skills.whatsapp_send import run
        result = run({"utterance": "send whatsapp to John: running late"})
        assert "Sent" in result
        mock_send.assert_called_once_with("+491701234567", "running late")


def test_whatsapp_send_unknown_contact():
    with patch("backend.modules.memory.store.MemoryStore.search_facts", return_value=[]):
        from backend.skills.whatsapp_send import run
        result = run({"utterance": "send whatsapp to Ghost: hello"})
        assert "don't have a phone number" in result.lower()


def test_whatsapp_send_unparseable_utterance():
    from backend.skills.whatsapp_send import run
    result = run({"utterance": "send whatsapp"})
    assert "didn't catch" in result.lower()


def test_whatsapp_send_self_test():
    from backend.skills.whatsapp_send import self_test
    assert self_test()
