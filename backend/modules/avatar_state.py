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

import re
import time
from pathlib import Path

# Gesture names the 3D avatar can actually perform. Mirrors TalkingHead's
# gestureTemplates (hand gestures) plus the 'yes'/'no' head animations.
KNOWN_GESTURES = frozenset({
    "handup", "index", "ok", "thumbup", "thumbdown", "side", "shrug", "namaste",
    "yes", "no",
})

# Full-body Mixamo clips live in frontend/animations/ and are served at
# /animations/<name>.fbx. They are DISCOVERED from disk rather than listed
# here, so dropping a new .fbx in that folder is all it takes to add a move.
ANIMATIONS_DIR: Path = Path(__file__).resolve().parents[2] / "frontend" / "animations"

# The name is pasted straight into a URL, so only accept tame filenames.
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Clips whose filename starts with this are used as ambient idle motion.
IDLE_PREFIX = "idle"

_cache: dict = {"names": frozenset(), "stamp": 0.0}
_CACHE_TTL = 10.0


def discover_animations(force: bool = False) -> frozenset[str]:
    """Names of the .fbx clips currently on disk (cached briefly)."""
    now = time.monotonic()
    if not force and (now - _cache["stamp"]) < _CACHE_TTL and _cache["names"]:
        return _cache["names"]
    names = set()
    try:
        for path in ANIMATIONS_DIR.glob("*.fbx"):
            stem = path.stem.lower()
            if _SAFE_NAME.match(stem):
                names.add(stem)
    except OSError:
        pass
    result = frozenset(names)
    _cache["names"], _cache["stamp"] = result, now
    return result


def known_animations() -> frozenset[str]:
    """Every playable clip. Falls back to the shipped set if the dir is gone."""
    return discover_animations() or BUILTIN_ANIMATIONS


def idle_animations() -> list[str]:
    """Clips suitable as ambient movement (filenames starting with 'idle')."""
    return sorted(n for n in known_animations() if n.startswith(IDLE_PREFIX))


# Shipped with the repo; used only as a fallback if the folder is unreadable.
BUILTIN_ANIMATIONS = frozenset({
    "walking", "start-walking", "jump", "waving", "talking",
    "arguing", "disappointed", "secret", "yelling",
})

_pending: dict = {"gesture": None, "animation": None, "routine": None, "ts": 0.0}


def request_gesture(name: str) -> bool:
    """Queue a hand/head gesture for the browser. False for unknown names."""
    if name not in KNOWN_GESTURES:
        return False
    _pending["gesture"] = name
    _pending["ts"] = time.monotonic()
    return True


def request_animation(name: str) -> bool:
    """Queue a full-body animation clip. False for unknown names."""
    if name not in known_animations():
        return False
    _pending["animation"] = name
    _pending["ts"] = time.monotonic()
    return True


def request_routine(names: list[str]) -> list[str]:
    """Queue a SEQUENCE of clips, performed one after another.

    Used by "show me everything you can do": a single clip answers that
    question with one example, which is not what was asked.
    Unknown names are dropped rather than failing the whole routine.
    """
    playable = [n for n in names if n in known_animations()]
    if not playable:
        return []
    _pending["routine"] = playable
    _pending["ts"] = time.monotonic()
    return playable


def pop_routine(max_age_s: float = 30.0) -> list[str] | None:
    """Return (once) the queued sequence of clips."""
    names = _pending["routine"]
    if names and (time.monotonic() - _pending["ts"]) <= max_age_s:
        _pending["routine"] = None
        return names
    return None


def _pop(key: str, max_age_s: float) -> str | None:
    name = _pending[key]
    if name and (time.monotonic() - _pending["ts"]) <= max_age_s:
        _pending[key] = None
        return name
    return None


def pop_gesture(max_age_s: float = 30.0) -> str | None:
    """Return (once) the queued gesture, if one was requested recently."""
    return _pop("gesture", max_age_s)


def pop_animation(max_age_s: float = 30.0) -> str | None:
    """Return (once) the queued full-body animation."""
    return _pop("animation", max_age_s)


def clear() -> None:
    """Drop anything queued (used by tests)."""
    _pending["gesture"] = None
    _pending["animation"] = None
    _pending["routine"] = None
    _pending["ts"] = 0.0
