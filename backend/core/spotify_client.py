"""Spotify Web API client — spotipy OAuth with PKCE.

One-time setup: python scripts/spotify_auth.py
Token cached by spotipy at .plasma/spotify_token (gitignored).
"""
from __future__ import annotations
import logging
import os

from backend.core.config import config

log = logging.getLogger("plasma.spotify")

_CACHE_PATH = str(config.PLASMA_DIR / "spotify_token")
_SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


def is_configured() -> bool:
    return bool(config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET)


def get_spotify():
    """Returns an authenticated spotipy.Spotify instance or raises RuntimeError."""
    if not is_configured():
        raise RuntimeError(
            "Spotify not configured. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env, "
            "then run: python scripts/spotify_auth.py"
        )
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        raise RuntimeError("spotipy not installed. Run: pip install spotipy")

    auth = SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=_SCOPE,
        cache_path=_CACHE_PATH,
        open_browser=False,
    )
    token = auth.get_cached_token()
    if not token:
        raise RuntimeError(
            "Spotify not authenticated. Run: python scripts/spotify_auth.py"
        )
    if auth.is_token_expired(token):
        token = auth.refresh_access_token(token["refresh_token"])

    return spotipy.Spotify(auth=token["access_token"])
