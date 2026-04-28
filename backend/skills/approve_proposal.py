"""Skill: approve_proposal — accept a pending skill proposal by name."""
from __future__ import annotations
import re
from backend.modules.skills.suggester import get_suggester


META = {
    "name": "approve_proposal",
    "description": "Approves a pending skill proposal and installs it.",
    "triggers": [
        "approve ",
        "accept ",
        "install ",
        "yes add the ",
    ],
}


def run(args=None):
    utterance = ((args or {}).get("utterance") or "").strip()
    m = re.search(
        r"(?:approve|accept|install|yes\s+add\s+the)\s+([a-z_]+)(?:\s+skill)?",
        utterance,
        re.IGNORECASE,
    )
    if not m:
        return "Which proposal should I approve?"
    name = m.group(1).strip().lower()
    return get_suggester().approve(name)


def self_test():
    return True