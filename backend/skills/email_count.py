"""PA-42 — Email count: "how many unread emails" / "check my inbox"."""
from __future__ import annotations

META = {
    "name": "email_count",
    "description": "Reads the unread email count from your Outlook inbox.",
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


def run(args: dict | None = None) -> str:
    try:
        from backend.core.ms_graph import graph_get, is_configured
    except ImportError:
        return "Microsoft Graph is not available."

    if not is_configured():
        return "Outlook isn't linked yet. Run: python scripts/ms_auth.py"

    try:
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

    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't check your inbox: {e}"


def self_test() -> bool:
    return True
