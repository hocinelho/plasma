"""Tests for PA-28 — PII redaction before cloud LLM calls."""
from __future__ import annotations
import pytest

from backend.modules.router.pii_redactor import redact, redact_messages


def test_empty_string():
    assert redact("") == ""


def test_passthrough_when_no_pii():
    text = "What's the weather like today?"
    assert redact(text) == text


def test_email():
    assert redact("Email me at hocine@example.com please") == "Email me at [EMAIL] please"


def test_multiple_emails():
    text = "From a@b.co to c.d-e@f.io"
    out = redact(text)
    assert "[EMAIL]" in out
    assert out.count("[EMAIL]") == 2
    assert "@" not in out


def test_phone_intl():
    out = redact("Call me on +49 1525 123 4567 tonight")
    assert "[PHONE]" in out
    assert "1525" not in out


def test_phone_us():
    out = redact("My number is (555) 123-4567")
    assert "[PHONE]" in out


def test_credit_card():
    out = redact("Charge 4111 1111 1111 1111 today")
    assert "[CARD]" in out
    assert "4111" not in out


def test_ipv4():
    out = redact("server lives at 192.168.1.42 over LAN")
    assert "[IP]" in out
    assert "192.168" not in out


def test_url():
    out = redact("Visit https://example.com/path?q=1 for details")
    assert "[URL]" in out
    assert "example.com" not in out


def test_long_id():
    out = redact("order 123456789012 was shipped")
    assert "[ID]" in out
    assert "123456789012" not in out


def test_short_numbers_kept():
    # 5-minute timer must not get clobbered
    assert redact("set a timer for 5 minutes") == "set a timer for 5 minutes"
    assert redact("year 2026") == "year 2026"


def test_redact_messages_preserves_role():
    msgs = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "my email is x@y.io"},
        {"role": "assistant", "content": "okay"},
    ]
    out = redact_messages(msgs)
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "user"
    assert out[1]["content"] == "my email is [EMAIL]"
    assert out[2]["content"] == "okay"


def test_redact_messages_keeps_extra_keys():
    msgs = [{"role": "user", "content": "call 555-867-5309", "tokens": 7}]
    out = redact_messages(msgs)
    assert out[0]["tokens"] == 7
    assert "[PHONE]" in out[0]["content"]


@pytest.mark.parametrize(
    "raw",
    [
        "send 100 dollars",
        "page 42 of the book",
        "year 2026 is fine",
        "I am 35 years old",
    ],
)
def test_normal_numbers_pass_through(raw):
    assert redact(raw) == raw
