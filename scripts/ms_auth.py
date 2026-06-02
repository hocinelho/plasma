"""One-time Microsoft account setup for Plasma Outlook integration.

Usage:
    python scripts/ms_auth.py

Prerequisites:
    1. Register an app at https://portal.azure.com
       - App registrations → New registration
       - Name: Plasma Voice Assistant
       - Supported account types: Personal Microsoft accounts (or your org's tenant)
       - No redirect URI needed (device code flow)
       - Under "Authentication": enable "Allow public client flows" = Yes
       - Under "API permissions": add Microsoft Graph → Delegated:
           Calendars.Read, Calendars.ReadWrite, Mail.Read
    2. Copy the Application (client) ID to .env:
           MS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    3. Run this script once. Your browser will open automatically.
       The token is saved to .plasma/ms_token.json (gitignored).

After that, calendar and email skills work hands-free by voice.
"""
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import config
from backend.core.ms_graph import AUTHORITY, SCOPES, TOKEN_CACHE_PATH


def main() -> None:
    if not config.MS_CLIENT_ID:
        print("ERROR: MS_CLIENT_ID is not set in your .env file.")
        print("  1. Register an app at portal.azure.com (see instructions above)")
        print("  2. Add MS_CLIENT_ID=<your-app-id> to .env")
        sys.exit(1)

    try:
        import msal
    except ImportError:
        print("ERROR: msal not installed. Run:  pip install msal")
        sys.exit(1)

    print("Starting Microsoft device-code authentication...")
    print(f"  Authority : {AUTHORITY}")
    print(f"  Scopes    : {', '.join(SCOPES)}\n")

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(
        config.MS_CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print("ERROR: Could not initiate device flow:", flow.get("error_description"))
        sys.exit(1)

    # Print the instructions (msal includes the URL and code in flow["message"])
    print(flow["message"])
    print("\nWaiting for you to sign in...", flush=True)

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")
        account = result.get("id_token_claims", {})
        name = account.get("name") or account.get("preferred_username") or "your account"
        print(f"\nAuthenticated as: {name}")
        print(f"Token saved to: {TOKEN_CACHE_PATH}")
        print("\nPlasma can now read your Outlook calendar and email by voice.")
    else:
        print("\nAuthentication failed:")
        print(f"  {result.get('error')}: {result.get('error_description')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
