"""PA-42 — Email count: "how many unread emails" / "check my inbox"."""
from __future__ import annotations

META = {
    "name": "email_count",
    "description": "Reads the unread email count from your Gmail / Outlook inbox.",
    "triggers": [
        "how many emails",
        "how many unread",
        "unread emails",
        "check my email",
        "check my inbox",
        "any new emails",
        "any emails",
        "my inbox",
        "new emails",
        "do i have email",
    ],
}


def _gmail_unread_count() -> str:
    """Get unread count from Gmail using the Labels endpoint."""
    from backend.core.google_client import google_get

    data = google_get(
        "https://www.googleapis.com/gmail/v1/users/me/labels/INBOX",
    )
    count = data.get("messagesUnread", 0)

    if count == 0:
        return "Your inbox is clear — no unread emails."
    if count == 1:
        return "You have 1 unread email in your inbox."
    return f"You have {count} unread emails in your inbox."


def _outlook_unread_count() -> str:
    """Get unread count from Outlook via MS Graph."""
    from backend.core.ms_graph import graph_get

    data = graph_get(
        "mailFolders/inbox/messages",
        **{
            "$filter": "isRead eq false",
            "$count": "true",
            "$top": "1",
            "$select": "id",
        },
    )
    count = data.get("@odata.count", None)
    if count is None:
        # Fallback: count returned items (limited to $top)
        count = len(data.get("value", []))
        return f"You have at least {count} unread email{'s' if count != 1 else ''} in your inbox."

    if count == 0:
        return "Your inbox is clear — no unread emails."
    if count == 1:
        return "You have 1 unread email in your inbox."
    return f"You have {count} unread emails in your inbox."


def run(args: dict | None = None) -> str:
    # Try Gmail first
    try:
        from backend.core.google_client import is_configured as google_configured
        if google_configured():
            try:
                return _gmail_unread_count()
            except Exception as e:
                return f"Couldn't check your Gmail: {e}"
    except ImportError:
        pass

    # Fall back to Microsoft Graph
    try:
        from backend.core.ms_graph import is_configured as ms_configured
        if ms_configured():
            try:
                return _outlook_unread_count()
            except RuntimeError as e:
                return str(e)
            except Exception as e:
                return f"Couldn't check your inbox: {e}"
    except ImportError:
        pass

    return (
        "No email linked yet. Run:\n"
        "  python scripts/google_auth.py   (Gmail)\n"
        "  python scripts/ms_auth.py       (Outlook)"
    )


def self_test() -> bool:
    return True
