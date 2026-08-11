"""Shared avatar state between skills and the HTTP layer.

Why this module exists
----------------------
`SkillRegistry` loads each skill file with `importlib.util.spec_from_file_location`
under a synthetic module name (`plasma_skill_<stem>`). That object is NOT the same
one you get from `from backend.skills import avatar_move` — Python builds a second,
independent module with its own globals.

So a skill that stashes state in its own module-level variable can never hand it to
`backend/main.py`: the skill writes to one copy, main.py reads an empty other copy.

Anything a skill needs to pass to the response therefore lives here instead. Both
sides reach this module through the normal import system, so both see one instance.
"""
from __future__ import annotations

import time

# Gesture names the 3D avatar can actually perform. Mirrors TalkingHead's
# gestureTemplates (hand gestures) plus the 'yes'/'no' head animations.
KNOWN_GESTURES = frozenset({
    "handup", "index", "ok", "thumbup", "thumbdown", "side", "shrug", "namaste",
    "yes", "no",
})

_pending: dict = {"gesture": None, "ts": 0.0}


def request_gesture(name: str) -> bool:
    """Queue a gesture for the browser. Returns False for unknown names."""
    if name not in KNOWN_GESTURES:
        return False
    _pending["gesture"] = name
    _pending["ts"] = time.monotonic()
    return True


def pop_gesture(max_age_s: float = 30.0) -> str | None:
    """Return (once) the queued gesture, if one was requested recently."""
    name = _pending["gesture"]
    if name and (time.monotonic() - _pending["ts"]) <= max_age_s:
        _pending["gesture"] = None
        return name
    return None


def clear() -> None:
    """Drop any queued gesture (used by tests)."""
    _pending["gesture"] = None
    _pending["ts"] = 0.0
