"""PA-78 — Slack: "what's the latest message in #general" / read a channel."""
from __future__ import annotations
import re

META = {
    "name": "slack_read",
    "description": "Reads the latest message in a Slack channel.",
    "triggers": [
        "latest slack message",
        "latest message in slack",
        "what's the latest in slack",
        "what is the latest in slack",
        "check slack",
        "read slack",
        "slack channel",
        "neueste slack nachricht",
        "letzte slack nachricht",
        "was steht in slack",
        "slack nachricht",
    ],
}

# "in #general", "in the general channel", "in general"
_CHANNEL_RE = re.compile(
    r"(?:in|im)\s+(?:the\s+)?#?([a-z0-9_-]+)(?:\s+channel)?",
    re.I,
)
_DEFAULT_CHANNEL = "general"


def _extract_channel(utterance: str) -> str:
    for m in _CHANNEL_RE.finditer(utterance):
        name = m.group(1).lower().strip()
        if name not in ("the", "slack"):
            return name
    return _DEFAULT_CHANNEL


def _find_channel_id(name: str) -> str | None:
    from backend.core.slack_client import slack_get

    data = slack_get(
        "conversations.list",
        types="public_channel,private_channel",
        limit="1000",
    )
    for ch in data.get("channels", []):
        if ch.get("name", "").lower() == name.lower():
            return ch.get("id")
    return None


def _user_name(user_id: str) -> str:
    from backend.core.slack_client import slack_get

    try:
        data = slack_get("users.info", user=user_id)
        user = data.get("user", {})
        return user.get("real_name") or user.get("name") or "Someone"
    except Exception:
        return "Someone"


def _read_latest_message(channel_name: str) -> str:
    from backend.core.slack_client import slack_get

    channel_id = _find_channel_id(channel_name)
    if channel_id is None:
        return f"I couldn't find a Slack channel named '{channel_name}'."

    history = slack_get("conversations.history", channel=channel_id, limit="1")
    messages = history.get("messages", [])
    if not messages:
        return f"No messages yet in #{channel_name}."

    msg = messages[0]
    text = (msg.get("text") or "").strip()
    if not text:
        return f"The latest message in #{channel_name} has no text (likely an attachment)."

    author = _user_name(msg["user"]) if msg.get("user") else "Someone"
    return f"In #{channel_name}, {author} said: {text}"


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    channel = _extract_channel(utterance)

    try:
        from backend.core.slack_client import is_configured
        if not is_configured():
            return "Slack isn't linked yet. Set SLACK_USER_TOKEN in your .env file."
        return _read_latest_message(channel)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't read Slack: {e}"


def self_test() -> bool:
    assert _extract_channel("what's the latest in slack in #engineering") == "engineering"
    assert _extract_channel("check slack in the marketing channel") == "marketing"
    assert _extract_channel("check slack") == _DEFAULT_CHANNEL
    return True
