"""Shopping list skill — persistent JSON store under .plasma/shopping.json.

Supports English and German. Actions: add, remove, show, clear.
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("plasma.skill.shopping_list")

_LIST_FILE = Path(__file__).resolve().parents[2] / ".plasma" / "shopping.json"

META = {
    "name": "shopping_list",
    "description": "Manage a persistent shopping list (add, remove, show, clear).",
    "triggers": [
        # English
        "add to my shopping list",
        "add to the shopping list",
        "add to shopping list",
        "remove from shopping list",
        "remove from my shopping list",
        "what's on my shopping list",
        "show my shopping list",
        "show shopping list",
        "shopping list",
        "clear my shopping list",
        "clear the shopping list",
        "delete from shopping list",
        "i need to buy",
        "buy ",
        # German
        "zur einkaufsliste hinzufügen",
        "einkaufsliste zeigen",
        "zeig meine einkaufsliste",
        "was steht auf meiner einkaufsliste",
        "von der einkaufsliste entfernen",
        "einkaufsliste leeren",
        "ich brauche",
        "kauf ",
    ],
    "example_utterances": [
        "Add milk to my shopping list",
        "What's on my shopping list?",
        "Remove eggs from shopping list",
        "Clear my shopping list",
        "Zur Einkaufsliste hinzufügen: Brot",
    ],
}

_ADD_EN = re.compile(
    r"(?:add|put|i need(?:\s+to\s+buy)?)\s+(.+?)\s+(?:to|on|onto)\s+(?:my\s+)?(?:the\s+)?shopping\s+list",
    re.I,
)
_ADD_BUY_EN = re.compile(r"(?:^|\bi need to buy\b)\s+(.+?)(?:\s*[.?!])?$", re.I)
_REMOVE_EN = re.compile(
    r"(?:remove|delete|take off)\s+(.+?)\s+from\s+(?:my\s+)?(?:the\s+)?shopping\s+list",
    re.I,
)
_SHOW_EN = re.compile(
    r"(?:what(?:'s| is) on|show|list|display)\s+(?:my\s+)?(?:the\s+)?shopping\s+list",
    re.I,
)
_CLEAR_EN = re.compile(r"(?:clear|empty|delete|wipe)\s+(?:my\s+)?(?:the\s+)?shopping\s+list", re.I)

_ADD_DE = re.compile(
    r"(?:zur\s+einkaufsliste\s+hinzufügen[:\s]+|(?:ich brauche|kauf(?:e)?)\s+)(.+?)(?:\s*[.?!])?$",
    re.I,
)
_REMOVE_DE = re.compile(r"von\s+der\s+einkaufsliste\s+entfernen[:\s]+(.+?)(?:\s*[.?!])?$", re.I)
_SHOW_DE = re.compile(r"(?:zeig|was steht auf meiner|einkaufsliste zeigen)", re.I)
_CLEAR_DE = re.compile(r"einkaufsliste\s+leeren", re.I)


def _load() -> list[str]:
    try:
        if _LIST_FILE.exists():
            return json.loads(_LIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed to load shopping list: %s", e)
    return []


def _save(items: list[str]) -> None:
    try:
        _LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LIST_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("Failed to save shopping list: %s", e)


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    items = _load()

    # Show
    if _SHOW_EN.search(utterance) or _SHOW_DE.search(utterance):
        if not items:
            return "Deine Einkaufsliste ist leer." if de else "Your shopping list is empty."
        listed = ", ".join(items)
        return f"Deine Einkaufsliste: {listed}." if de else f"Your shopping list: {listed}."

    # Clear
    if _CLEAR_EN.search(utterance) or _CLEAR_DE.search(utterance):
        _save([])
        return "Einkaufsliste geleert." if de else "Shopping list cleared."

    # Remove
    m = _REMOVE_EN.search(utterance) or _REMOVE_DE.search(utterance)
    if m:
        item = m.group(1).strip().lower()
        before = len(items)
        items = [x for x in items if x.lower() != item]
        if len(items) < before:
            _save(items)
            return f"{item.capitalize()} entfernt." if de else f"Removed {item} from your shopping list."
        return f"{item.capitalize()} war nicht auf der Liste." if de else f"{item.capitalize()} wasn't on the list."

    # Add (English patterns)
    m = _ADD_EN.search(utterance)
    if not m:
        m = _ADD_BUY_EN.search(utterance) if re.search(r"\bi need to buy\b", utterance, re.I) else None
    # Add (German patterns)
    if not m:
        m = _ADD_DE.search(utterance)
    if m:
        item = m.group(1).strip().rstrip(".,!?").lower()
        if item and item not in [x.lower() for x in items]:
            items.append(item)
            _save(items)
        return f"{item.capitalize()} zur Einkaufsliste hinzugefügt." if de else f"Added {item} to your shopping list."

    # Fallback: if "shopping list" mentioned, treat rest as item to add
    if "shopping list" in utterance.lower() or "einkaufsliste" in utterance.lower():
        parts = re.split(r"shopping list|einkaufsliste", utterance, flags=re.I)
        candidate = parts[-1].strip().lstrip(":, ").rstrip(".,!?").lower() if len(parts) > 1 else ""
        if candidate:
            if candidate not in [x.lower() for x in items]:
                items.append(candidate)
                _save(items)
            return f"{candidate.capitalize()} zur Einkaufsliste hinzugefügt." if de else f"Added {candidate} to your shopping list."

    return (
        "Sag z.B. 'Milch zur Einkaufsliste hinzufügen' oder 'Zeig meine Einkaufsliste'."
        if de
        else "Try: 'add milk to my shopping list', 'show my shopping list', or 'remove eggs from shopping list'."
    )


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
