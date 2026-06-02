"""PA-60 — Voice notes: "take a note buy milk" / "read my notes"."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

from backend.core.config import config

META = {
    "name": "voice_notes",
    "description": "Saves and reads voice notes stored locally.",
    "triggers": [
        "take a note",
        "note this",
        "write this down",
        "write down",
        "save a note",
        "note that",
        "read my notes",
        "show my notes",
        "what are my notes",
        "clear my notes",
        "delete my notes",
    ],
}

_NOTES_FILE = config.PLASMA_DIR / "notes.jsonl"

_STRIP = re.compile(
    r"^(?:take\s+a?\s*note|note\s+this|write\s+(?:this\s+)?down|"
    r"save\s+a?\s*note|note\s+that)[:\s]+",
    re.I,
)
_READ_RE = re.compile(r"\b(read|show|what\s+are|list)\b.*\bnotes?\b", re.I)
_CLEAR_RE = re.compile(r"\b(clear|delete|remove|erase)\b.*\bnotes?\b", re.I)


def _save(text: str) -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "text": text}) + "\n")


def _read_all() -> list[str]:
    if not _NOTES_FILE.exists():
        return []
    notes = []
    for line in _NOTES_FILE.read_text(encoding="utf-8").splitlines():
        try:
            notes.append(json.loads(line)["text"])
        except Exception:
            pass
    return notes


def _clear() -> None:
    if _NOTES_FILE.exists():
        _NOTES_FILE.unlink()


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "").strip()

    if _CLEAR_RE.search(utterance):
        _clear()
        return "All your notes have been deleted."

    if _READ_RE.search(utterance):
        notes = _read_all()
        if not notes:
            return "You have no saved notes."
        if len(notes) == 1:
            return f"You have 1 note: {notes[0]}."
        joined = "; ".join(notes)
        return f"You have {len(notes)} notes: {joined}."

    # Save note
    text = _STRIP.sub("", utterance).strip(" ?.")
    if not text:
        return "What would you like me to note down?"
    _save(text)
    return f"Note saved: {text}."


def self_test() -> bool:
    import tempfile, os
    tmp = Path(tempfile.mktemp(suffix=".jsonl"))
    orig = _NOTES_FILE
    # Patch the path temporarily
    import backend.skills.voice_notes as mod
    mod._NOTES_FILE = tmp
    try:
        mod._save("test note")
        notes = mod._read_all()
        assert notes == ["test note"]
        mod._clear()
        assert mod._read_all() == []
        return True
    finally:
        mod._NOTES_FILE = orig
        if tmp.exists():
            tmp.unlink()
