"""Skill: list_proposals — read out pending skill proposals."""
from __future__ import annotations
from backend.modules.skills.suggester import get_suggester


META = {
    "name": "list_proposals",
    "description": "Lists pending skill proposals.",
    "triggers": [
        "show proposals",
        "list proposals",
        "what skills do you suggest",
        "any new skills",
    ],
}


def run(args=None):
    proposals = [p for p in get_suggester().list_proposals() if p["status"] == "pending"]
    if not proposals:
        return "I don't have any pending skill proposals."
    names = [p["name"] for p in proposals]
    if len(names) == 1:
        return f"I'm suggesting one new skill: {names[0]}. Say 'approve {names[0]} skill' to accept."
    joined = ", ".join(names)
    return f"I'm suggesting these skills: {joined}. Say 'approve <name> skill' to accept any of them."


def self_test():
    return True