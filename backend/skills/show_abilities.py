"""Skill: show_abilities — "what movements can you do?"

Lists the moves she actually has, read from the animation folder at the time
of asking, so the answer can never drift out of date when clips are added or
removed. Optionally demonstrates one.
"""
from __future__ import annotations

import random

from backend.modules.avatar_state import (
    KNOWN_GESTURES,
    known_animations,
    request_routine,
)

META = {
    "name": "show_abilities",
    "description": "Lists the movements and gestures the avatar can perform.",
    "triggers": [
        # English
        "what movements", "what movement", "what moves can you",
        "show me what you can do", "show me your moves", "what can you do",
        "which movements", "list your moves", "what moves do you know",
        "show me what movement", "what are your moves",
        # German
        "welche bewegungen", "was kannst du machen", "zeig mir was du kannst",
        "welche moves", "was für bewegungen",
    ],
    "example_utterances": [
        "Show me what movements you can do",
        "What moves do you know?",
        "Welche Bewegungen kannst du?",
    ],
}

# Human-readable names for the clips, so she says "the samba" not
# "dance-samba". Anything not listed is de-hyphenated automatically.
FRIENDLY = {
    "dance-samba": ("the samba", "Samba"),
    "dance-gangnam": ("gangnam style", "Gangnam Style"),
    "start-walking": ("start walking", "losgehen"),
    "walk-back": ("walk backwards", "rückwärts gehen"),
    "walk-left": ("step left", "nach links gehen"),
    "walk-right": ("step right", "nach rechts gehen"),
    "turn-left": ("turn left", "mich nach links drehen"),
    "turn-right": ("turn right", "mich nach rechts drehen"),
    "backflip": ("a backflip", "einen Salto"),
    "talking": ("talk with my hands", "mit den Händen reden"),
    "secret": ("whisper a secret", "ein Geheimnis flüstern"),
    "arguing": ("argue", "argumentieren"),
    "disappointed": ("look disappointed", "enttäuscht schauen"),
    "yelling": ("yell", "schreien"),
    "waving": ("wave", "winken"),
    "walking": ("walk", "laufen"),
    "running": ("run", "rennen"),
    "sprint": ("sprint", "sprinten"),
    "jump": ("jump", "springen"),
}

# Gestures are arm/head only; named separately so the answer stays honest
# about the difference between a wave and a whole-body move.
GESTURE_NAMES = {
    "handup": ("wave", "winken"),
    "thumbup": ("give a thumbs up", "Daumen hoch geben"),
    "thumbdown": ("give a thumbs down", "Daumen runter geben"),
    "ok": ("make an OK sign", "OK zeigen"),
    "index": ("point", "zeigen"),
    "shrug": ("shrug", "mit den Schultern zucken"),
    "namaste": ("bow", "mich verbeugen"),
    "yes": ("nod", "nicken"),
    "no": ("shake my head", "den Kopf schütteln"),
}

# Idle clips are ambient background motion, not something to announce.
_HIDDEN_PREFIX = "idle"


def _friendly(name: str, german: bool) -> str:
    if name in FRIENDLY:
        return FRIENDLY[name][1 if german else 0]
    return name.replace("-", " ")


def _listed_animations(german: bool) -> list[str]:
    names = sorted(n for n in known_animations() if not n.startswith(_HIDDEN_PREFIX))
    return [_friendly(n, german) for n in names]


def _join(items: list[str], german: bool) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    last = "und" if german else "and"
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def run(args: dict | None = None) -> str:
    args = args or {}
    german = args.get("language") == "de"

    moves = _listed_animations(german)
    gestures = [
        (GESTURE_NAMES[g][1 if german else 0])
        for g in sorted(KNOWN_GESTURES) if g in GESTURE_NAMES
    ]

    # Perform them all, one after another — asked "show me what you can do",
    # a single example is not an answer. Ordered so it builds to the dances.
    routine = sorted(
        (n for n in known_animations() if not n.startswith(_HIDDEN_PREFIX)),
        key=lambda n: (n.startswith("dance"), n.startswith("backflip"), n),
    )
    if routine:
        request_routine(routine)

    if german:
        return (
            f"Ganzkörper kann ich: {_join(moves, True)}. "
            f"Dazu mit Händen und Kopf: {_join(gestures, True)}. "
            f"Ich zeige dir jetzt alles der Reihe nach."
        )
    return (
        f"Full body, I can: {_join(moves, False)}. "
        f"With my hands and head: {_join(gestures, False)}. "
        f"Watch, I'll go through them all now."
    )


def self_test() -> bool:
    reply = run({})
    if not isinstance(reply, str) or len(reply) < 40:
        return False
    # Must name real moves, and must not leak internal clip names or the
    # ambient idle clips.
    if "dance-samba" in reply or "idle" in reply.lower():
        return False
    if "samba" not in reply:
        return False
    de = run({"language": "de"})
    return "Ganzkörper" in de and "Samba" in de
