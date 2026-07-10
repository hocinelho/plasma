"""
PII redaction layer — strip personally identifying info before cloud LLM calls.

Plasma's local Ollama path keeps everything on the user's machine. Once
Step 9 enables cloud providers (Groq, Claude), the user's voice transcript
and memory facts may be sent to a third party. This module is the safety
gate: every cloud-bound payload is run through `redact()` first.

Redacted classes:
  - Email addresses           → [EMAIL]
  - Phone numbers (intl/US)   → [PHONE]
  - Credit-card-shaped runs   → [CARD]
  - IPv4 addresses            → [IP]
  - URLs (http/https)         → [URL]
  - 9+ digit ID-like runs     → [ID]

Names and addresses are intentionally NOT redacted — Whisper transcripts
don't reliably mark them and false-positives ruin meaning. USER.md is
read once at startup, so the user can review what gets sent.
"""
from __future__ import annotations
import logging
import re

log = logging.getLogger("plasma.pii_redactor")

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"https?://[^\s)>\"']+", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CARD = re.compile(r"(?<!\d)\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{3,4}(?!\d)")
_PHONE_INTL = re.compile(r"(?<!\w)\+\d[\d\s\.\-]{7,17}\d(?!\w)")
_PHONE_GROUPED = re.compile(
    r"(?<!\d)\(?\d{3}\)?[\s\.\-]\d{3}[\s\.\-]\d{4}(?!\d)"
)
_LONG_ID = re.compile(r"(?<!\d)\d{9,}(?!\d)")


def redact(text: str) -> str:
    """Return `text` with PII replaced by class placeholders.

    Order: URL → EMAIL → CARD (4-4-4-4) → IPv4 → +intl phone →
    grouped phone (xxx-xxx-xxxx) → bare long digit IDs.
    """
    if not text:
        return text
    out = _URL.sub("[URL]", text)
    out = _EMAIL.sub("[EMAIL]", out)
    out = _CARD.sub("[CARD]", out)
    out = _IPV4.sub("[IP]", out)
    out = _PHONE_INTL.sub("[PHONE]", out)
    out = _PHONE_GROUPED.sub("[PHONE]", out)
    out = _LONG_ID.sub("[ID]", out)
    return out


def redact_messages(messages: list[dict]) -> list[dict]:
    """Redact the `content` field of every message in an OpenAI-style list."""
    redacted: list[dict] = []
    for m in messages:
        content = m.get("content", "")
        redacted.append({**m, "content": redact(content)})
    return redacted
