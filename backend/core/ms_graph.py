"""Microsoft Graph API client — MSAL device-code auth + token cache.

One-time setup: python scripts/ms_auth.py
Token persisted at .plasma/ms_token.json (gitignored).
"""
from __future__ import annotations
import json
import logging
from typing import Optional

from backend.core.config import config
from backend.core.http_client import get as _http_get, _VERIFY

log = logging.getLogger("plasma.ms_graph")

_AUTHORITY = f"https://login.microsoftonline.com/{config.MS_TENANT_ID}"
_SCOPES = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Mail.Read",
]
_GRAPH = "https://graph.microsoft.com/v1.0/me"
TOKEN_CACHE_PATH = config.PLASMA_DIR / "ms_token.json"
AUTHORITY = _AUTHORITY
SCOPES = _SCOPES


def _app_and_cache():
    try:
        import msal
    except ImportError:
        raise RuntimeError("msal not installed. Run: pip install msal")
    import msal

    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_PATH.exists():
        cache.deserialize(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        config.MS_CLIENT_ID,
        authority=_AUTHORITY,
        token_cache=cache,
    )
    return app, cache


def _save_cache(cache) -> None:
    if cache.has_state_changed:
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")


def is_configured() -> bool:
    return bool(config.MS_CLIENT_ID) and TOKEN_CACHE_PATH.exists()


def get_access_token() -> Optional[str]:
    if not config.MS_CLIENT_ID:
        return None
    try:
        app, cache = _app_and_cache()
        accounts = app.get_accounts()
        if not accounts:
            return None
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]
    except Exception as e:
        log.warning(f"MS token refresh failed: {e}")
    return None


def _headers() -> dict:
    token = get_access_token()
    if not token:
        raise RuntimeError(
            "Microsoft account not linked. Run: python scripts/ms_auth.py"
        )
    return {"Authorization": f"Bearer {token}"}


def graph_get(path: str, **params) -> dict:
    """GET /v1.0/me/{path} with auth."""
    import httpx

    resp = httpx.get(
        f"{_GRAPH}/{path.lstrip('/')}",
        headers=_headers(),
        params=params or None,
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    return resp.json()


def graph_post(path: str, body: dict) -> dict:
    """POST /v1.0/me/{path} with auth."""
    import httpx

    resp = httpx.post(
        f"{_GRAPH}/{path.lstrip('/')}",
        headers={**_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=10.0,
        verify=_VERIFY,
    )
    resp.raise_for_status()
    return resp.json()
