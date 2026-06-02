"""One-time Spotify authentication setup for Plasma.

Usage:
    python scripts/spotify_auth.py

Prerequisites:
    1. Go to https://developer.spotify.com/dashboard
    2. Create an app (any name, e.g. "Plasma Voice Assistant")
    3. In app settings, add Redirect URI: http://127.0.0.1:9090
    4. Copy Client ID and Client Secret to .env:
           SPOTIFY_CLIENT_ID=xxxxxxxxxxxxxxxxxxxx
           SPOTIFY_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxx
    5. Run this script — a browser window opens, click Authorize
       Token cached to .plasma/spotify_token (gitignored)

Requires Spotify Premium for playback control (play/pause/next/previous).
'What song is playing' works on free accounts.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import config
from backend.core.spotify_client import _CACHE_PATH, _SCOPE


def main() -> None:
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        print("ERROR: SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not set in .env")
        print("  See https://developer.spotify.com/dashboard to create an app.")
        sys.exit(1)

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        print("ERROR: spotipy not installed. Run: pip install spotipy")
        sys.exit(1)

    config.PLASMA_DIR.mkdir(parents=True, exist_ok=True)

    print("Opening browser for Spotify authorization...")
    print(f"  Redirect URI : {config.SPOTIFY_REDIRECT_URI}")
    print(f"  Scopes       : {_SCOPE}\n")

    auth = SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=_SCOPE,
        cache_path=_CACHE_PATH,
        open_browser=True,
    )

    token = auth.get_access_token(as_dict=False)
    if token:
        config.PLASMA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\nToken saved to: {_CACHE_PATH}")
        try:
            sp = spotipy.Spotify(auth=token)
            me = sp.current_user()
            print(f"Authenticated as: {me['display_name']}")
        except Exception:
            print("Authenticated. (Profile info unavailable — Spotify Premium required)")
        print("\nNote: Spotify playback control and 'what song is playing' require Premium.")
    else:
        print("\nAuthentication failed. Check your Client ID and Secret.")
        sys.exit(1)


if __name__ == "__main__":
    main()
