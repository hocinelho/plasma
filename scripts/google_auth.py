"""One-time Google account setup for Plasma Calendar + Gmail integration.

Usage:
    python scripts/google_auth.py

Prerequisites:
    1. Create a project at https://console.cloud.google.com
       - Enable: Google Calendar API, Gmail API
       - Go to "Credentials" → Create OAuth 2.0 Client ID (Desktop app)
    2. Copy the Client ID and Client Secret to .env:
           GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
           GOOGLE_CLIENT_SECRET=your_client_secret
    3. Run this script once. Your browser will open for consent.
       The token is saved to .plasma/google_token.json (gitignored).

After that, calendar and email skills work hands-free by voice.
"""
import json
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import config

_TOKEN_PATH = config.PLASMA_DIR / "google_token.json"
_REDIRECT_PORT = 8085
_REDIRECT_URI = f"http://127.0.0.1:{_REDIRECT_PORT}"
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Will be set by the callback handler
_auth_code = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth2 redirect callback."""

    def do_GET(self):
        global _auth_code
        query = parse_qs(urlparse(self.path).query)

        if "error" in query:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = query["error"][0]
            self.wfile.write(
                f"<h2>Authentication failed</h2><p>{error}</p>".encode()
            )
            _auth_code = None
            return

        if "code" in query:
            _auth_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h2>Success!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>No authorization code received.</h2>")

    def log_message(self, format, *args):
        """Suppress default HTTP request logging."""
        pass


def main() -> None:
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set in your .env file.")
        print("  1. Create a project at https://console.cloud.google.com")
        print("  2. Enable Google Calendar API and Gmail API")
        print("  3. Create OAuth 2.0 credentials (Desktop app)")
        print("  4. Add to .env:")
        print("       GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com")
        print("       GOOGLE_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    # Build the authorization URL
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{_AUTH_ENDPOINT}?{urlencode(params)}"

    print("Starting Google OAuth2 authentication...")
    print(f"  Scopes: {', '.join(_SCOPES)}\n")
    print("Opening your browser for consent...")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    # Start local server to catch the redirect
    server = HTTPServer(("127.0.0.1", _REDIRECT_PORT), _CallbackHandler)
    print(f"Waiting for callback on http://127.0.0.1:{_REDIRECT_PORT} ...", flush=True)
    server.handle_request()  # Handle exactly one request
    server.server_close()

    if not _auth_code:
        print("\nAuthentication failed — no authorization code received.")
        sys.exit(1)

    # Exchange authorization code for tokens
    print("\nExchanging authorization code for tokens...")
    import httpx

    resp = httpx.post(
        _TOKEN_ENDPOINT,
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": _auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": _REDIRECT_URI,
        },
        timeout=15.0,
    )

    if resp.status_code != 200:
        print(f"\nToken exchange failed ({resp.status_code}):")
        print(f"  {resp.text}")
        sys.exit(1)

    result = resp.json()

    if "access_token" not in result:
        print(f"\nUnexpected response: {result}")
        sys.exit(1)

    token_data = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "token_uri": _TOKEN_ENDPOINT,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "expiry": time.time() + result.get("expires_in", 3600),
    }

    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")

    print(f"\nToken saved to: {_TOKEN_PATH}")
    print("\nPlasma can now read your Google Calendar and Gmail by voice.")


if __name__ == "__main__":
    main()
