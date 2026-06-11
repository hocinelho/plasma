"""Google API client — lightweight OAuth2 with httpx (no heavy SDKs).

One-time setup: python scripts/google_auth.py
Token persisted at .plasma/google_token.json (gitignored).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from backend.core.config import config
from backend.core.http_client import _VERIFY

log = logging.getLogger("plasma.google_client")

TOKEN_PATH = config.PLASMA_DIR / "google_token.json"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def is_configured() -> bool:
    """True if Google OAuth credentials are available and token exists."""
    return TOKEN_PATH.exists()


def _load_token() -> Optional[dict]:
    """Load saved token data from disk."""
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Could not read Google token: {e}")
        return None


def _save_token(token_data: dict) -> None:
    """Persist token data to disk."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def _refresh_if_needed(token_data: dict) -> dict:
    """Check expiry and refresh the access token if needed."""
    import httpx

    expiry = token_data.get("expiry", 0)
    # Refresh if token expires within the next 60 seconds
    if time.time() < expiry - 60:
        return token_data

    refresh_token = token_data.get("refresh_token")
    client_id = token_data.get("client_id") or config.GOOGLE_CLIENT_ID
    client_secret = token_data.get("client_secret") or config.GOOGLE_CLIENT_SECRET

    if not refresh_token:
        raise RuntimeError(
            "Google refresh token missing. Re-run: python scripts/google_auth.py"
        )

    resp = httpx.post(
        _TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    result = resp.json()

    token_data["access_token"] = result["access_token"]
    token_data["expiry"] = time.time() + result.get("expires_in", 3600)
    # Google may rotate refresh tokens
    if "refresh_token" in result:
        token_data["refresh_token"] = result["refresh_token"]

    _save_token(token_data)
    return token_data


def _get_access_token() -> str:
    """Return a valid access token, refreshing if necessary."""
    token_data = _load_token()
    if not token_data:
        raise RuntimeError(
            "Google account not linked. Run: python scripts/google_auth.py"
        )
    token_data = _refresh_if_needed(token_data)
    return token_data["access_token"]


def _headers() -> dict:
    token = _get_access_token()
    return {"Authorization": f"Bearer {token}"}


def google_get(endpoint: str, **params) -> dict:
    """GET request to a Google API endpoint with auth."""
    import httpx

    resp = httpx.get(
        endpoint,
        headers=_headers(),
        params=params or None,
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    return resp.json()


def google_post(endpoint: str, body: dict) -> dict:
    """POST request to a Google API endpoint with auth."""
    import httpx

    resp = httpx.post(
        endpoint,
        headers={**_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    return resp.json()
