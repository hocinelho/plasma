"""Skill: reject_proposal — dismiss a pending skill proposal by name."""
from __future__ import annotations
import re
from backend.modules.skills.suggester import get_suggester


META = {
    "name": "reject_proposal",
    "description": "Rejects a pending skill proposal.",
    "triggers": [
        "reject ",
        "dismiss ",
        "no don't add the ",
    ],
}


def run(args=None):
    utterance = ((args or {}).get("utterance") or "").strip()
    m = re.search(
        r"(?:reject|dismiss|no\s+don't\s+add\s+the)\s+([a-z_]+)(?:\s+skill)?",
        utterance,
        re.IGNORECASE,
    )
    if not m:
        return "Which proposal should I reject?"
    name = m.group(1).strip().lower()
    return get_suggester().reject(name)


def self_test():
    return True