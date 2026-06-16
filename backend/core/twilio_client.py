"""Twilio WhatsApp client — REST API via httpx, no SDK dependency.

One-time setup: sign up at https://www.twilio.com, get a WhatsApp-enabled
number (sandbox or production), and set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
and TWILIO_WHATSAPP_FROM in .env.
"""
from __future__ import annotations
import logging

from backend.core.config import config
from backend.core.http_client import _VERIFY

log = logging.getLogger("plasma.twilio_client")


def is_configured() -> bool:
    return bool(
        config.TWILIO_ACCOUNT_SID
        and config.TWILIO_AUTH_TOKEN
        and config.TWILIO_WHATSAPP_FROM
    )


def send_whatsapp_message(to: str, body: str) -> dict:
    """POST a WhatsApp message via the Twilio Messages API.

    `to` must be a phone number in E.164 format (e.g. +491701234567);
    the whatsapp: prefix is added automatically.
    """
    import httpx

    if not is_configured():
        raise RuntimeError(
            "WhatsApp not linked. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_WHATSAPP_FROM in .env (see .env.example)."
        )

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{config.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    resp = httpx.post(
        url,
        auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
        data={
            "From": f"whatsapp:{config.TWILIO_WHATSAPP_FROM}",
            "To": f"whatsapp:{to}",
            "Body": body,
        },
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    return resp.json()
