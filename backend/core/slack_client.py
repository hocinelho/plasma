"""Slack Web API client — user token auth, no SDK dependency.

One-time setup: create a Slack app at https://api.slack.com/apps, install it
to your workspace, and copy the User OAuth Token (xoxp-...) into .env as
SLACK_USER_TOKEN.
"""
from __future__ import annotations
import logging

from backend.core.config import config
from backend.core.http_client import _VERIFY

log = logging.getLogger("plasma.slack_client")

_API = "https://slack.com/api"


def is_configured() -> bool:
    return bool(config.SLACK_USER_TOKEN)


def _headers() -> dict:
    if not config.SLACK_USER_TOKEN:
        raise RuntimeError(
            "Slack not linked. Set SLACK_USER_TOKEN in .env (see .env.example)."
        )
    return {"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"}


def slack_get(method: str, **params) -> dict:
    """GET https://slack.com/api/{method} with auth. Raises on Slack-level errors too."""
    import httpx

    resp = httpx.get(
        f"{_API}/{method.lstrip('/')}",
        headers=_headers(),
        params=params or None,
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
    return data
