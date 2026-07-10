"""PA-80 — WhatsApp: "send a whatsapp to John: I'm running late."

Sends via Twilio. The recipient can be a phone number directly, or a name
that's been saved to memory beforehand, e.g.:
    "Remember that John's number is +491701234567"
    "Send whatsapp to John: running 10 minutes late"
"""
from __future__ import annotations
import re

META = {
    "name": "whatsapp_send",
    "description": "Sends a WhatsApp message by voice via Twilio.",
    "triggers": [
        "send whatsapp",
        "send a whatsapp",
        "whatsapp message",
        "text on whatsapp",
        "message on whatsapp",
        "schreib eine whatsapp",
        "schreibe eine whatsapp",
        "sende eine whatsapp",
        "whatsapp nachricht",
    ],
}

# "to John: ..." / "to +491701234567 saying ..." / German "an John: ..."
_RECIPIENT_MSG_RE = re.compile(
    r"(?:to|an)\s+(.+?)\s*(?:[:,]|saying|that says|dass)\s*(.+)",
    re.I,
)
_PHONE_RE = re.compile(r"\+?\d[\d\s\-]{6,}\d")


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-]", "", raw)
    if not digits.startswith("+"):
        digits = "+" + digits
    return digits


def _parse(utterance: str) -> tuple[str, str] | None:
    m = _RECIPIENT_MSG_RE.search(utterance)
    if not m:
        return None
    recipient = m.group(1).strip().strip(".,")
    message = m.group(2).strip().rstrip(".?!").strip()
    if not recipient or not message:
        return None
    return recipient, message


def _resolve_phone(recipient: str) -> str | None:
    phone_match = _PHONE_RE.search(recipient)
    if phone_match:
        return _normalize_phone(phone_match.group(0))

    from backend.modules.memory.store import MemoryStore
    memory = MemoryStore()
    for fact in memory.search_facts(recipient, limit=5):
        phone_match = _PHONE_RE.search(fact.get("content", ""))
        if phone_match:
            return _normalize_phone(phone_match.group(0))
    return None


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    parsed = _parse(utterance)
    if parsed is None:
        return (
            "I didn't catch who to message or what to say. Try: "
            "'send whatsapp to John: running late'."
        )

    recipient, message = parsed
    phone = _resolve_phone(recipient)
    if phone is None:
        return (
            f"I don't have a phone number for {recipient}. Save it first: "
            f"'remember that {recipient}'s number is +1234567890'."
        )

    try:
        from backend.core.twilio_client import send_whatsapp_message
        send_whatsapp_message(phone, message)
        return f"Sent on WhatsApp to {recipient}: {message}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't send the WhatsApp message: {e}"


def self_test() -> bool:
    parsed = _parse("send whatsapp to John: running 10 minutes late")
    assert parsed == ("John", "running 10 minutes late")
    assert _normalize_phone("+49 170 1234567") == "+491701234567"
    assert _normalize_phone("491701234567") == "+491701234567"
    return True
