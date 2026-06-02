"""PA-61 — Todo list: "add buy milk to my list" / "what's on my list"."""
from __future__ import annotations
import json
import re
from pathlib import Path

from backend.core.config import config

META = {
    "name": "todo_list",
    "description": "Manages a voice-driven todo list stored locally.",
    "triggers": [
        "add to my list",
        "add to my todo",
        "add to the list",
        "put on my list",
        "my todo list",
        "what's on my list",
        "what is on my list",
        "read my list",
        "show my list",
        "clear my list",
        "delete my list",
        "mark as done",
    ],
}

_TODO_FILE = config.PLASMA_DIR / "todos.json"

_ADD_RE = re.compile(
    r"^(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my\s+)?(?:todo\s+)?list\b",
    re.I,
)
_ADD_COLON_RE = re.compile(
    r"^(?:add\s+to\s+(?:my\s+)?(?:todo\s+)?list|put\s+on\s+my\s+list)[:\s]+(.+)",
    re.I,
)
_READ_RE = re.compile(r"\b(read|show|what(?:'s|\s+is)\s+on|list)\b.*\blist\b", re.I)
_CLEAR_RE = re.compile(r"\b(clear|delete|remove|erase)\b.*\blist\b", re.I)
_DONE_RE = re.compile(r"\bmark\s+(?:as\s+)?done[:\s]+(.+)", re.I)


def _load() -> list[dict]:
    if not _TODO_FILE.exists():
        return []
    try:
        return json.loads(_TODO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TODO_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "").strip()
    items = _load()

    # Mark done
    m = _DONE_RE.search(utterance)
    if m:
        target = m.group(1).strip().lower()
        for item in items:
            if target in item["text"].lower():
                item["done"] = True
                _save(items)
                return f"Marked as done: {item['text']}."
        return f"I couldn't find '{target}' on your list."

    # Clear
    if _CLEAR_RE.search(utterance):
        _save([])
        return "Your todo list has been cleared."

    # Read
    if _READ_RE.search(utterance):
        pending = [i for i in items if not i.get("done")]
        if not pending:
            return "Your todo list is empty."
        if len(pending) == 1:
            return f"You have 1 todo: {pending[0]['text']}."
        joined = "; ".join(i["text"] for i in pending)
        return f"You have {len(pending)} todos: {joined}."

    # Add (colon form: "add to my list: buy milk")
    m = _ADD_COLON_RE.match(utterance)
    if m:
        text = m.group(1).strip(" ?.")
        items.append({"text": text, "done": False})
        _save(items)
        return f"Added to your list: {text}."

    # Add (natural form: "add buy milk to my list")
    m = _ADD_RE.match(utterance)
    if m:
        text = m.group(1).strip(" ?.")
        items.append({"text": text, "done": False})
        _save(items)
        return f"Added to your list: {text}."

    return "Try: 'add buy milk to my list' or 'what's on my list'."


def self_test() -> bool:
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".json"))
    import backend.skills.todo_list as mod
    orig = mod._TODO_FILE
    mod._TODO_FILE = tmp
    try:
        r = mod.run({"utterance": "add buy milk to my list"})
        assert "buy milk" in r.lower()
        items = mod._load()
        assert len(items) == 1
        r2 = mod.run({"utterance": "what's on my list"})
        assert "buy milk" in r2.lower()
        mod.run({"utterance": "clear my list"})
        assert mod._load() == []
        return True
    finally:
        mod._TODO_FILE = orig
        if tmp.exists():
            tmp.unlink()
