"""Meeting someone new: she notices, asks their name, and remembers it.

She could already greet a face she had been *told* about ("remember my face
as Hocine"). What was missing is the unprompted half — noticing a face she
does not know, asking who it is, and keeping the answer. That is the
difference between a lookup table and actually meeting someone.

The flow, across three files:

    main.py  (perception socket)  a face, no identity, several frames running
                                  → she asks, and marks AWAITING_NAME
    chat_service.py               the next thing said is routed back to the
                                  skill, with the marker passed through
    skills/vision_query.py        reads the name, enrols it from the live frame

The marker lives here rather than in the skill because the skill registry
loads skill files under synthetic module names (see avatar_state.py), so
importing the skill from main.py just to read one string would load a second
copy of it. Here, both sides import the same module the ordinary way.

The pacing constants live here too, next to the reason for each.
"""
from __future__ import annotations

# The pending-intent fact she writes when she asks. chat_service splits on the
# first ":" to find the skill, so the prefix must stay the skill's real name.
AWAITING_NAME = "vision_query:awaiting_name"

# How many consecutive frames a stranger must be visible before she says
# anything. Frames arrive at ~6/s, so this is about a second and a half of
# somebody actually standing there — long enough that walking past the camera,
# or one bad recognition of a person she does know, does not trigger it.
STRANGER_FRAMES = 9

# And how long before she may ask again. Being asked your name twice in a
# minute is worse than not being asked at all, and the commonest reason for
# no answer is that the person did not want to give one. Five minutes means a
# genuine second attempt is still possible in one sitting, but nagging is not.
ASK_COOLDOWN_S = 300.0


def question(de: bool = False) -> str:
    """What she says. Short on purpose — it is spoken, unprompted, at someone
    who did not ask for a conversation."""
    return ("Hallo! Dich kenne ich noch nicht. Wie heißt du?"
            if de else
            "Hello! I don't think we've met. What's your name?")


def arm(session_id: str | None = None) -> bool:
    """Mark that she has asked, so the next thing said is read as an answer.

    Uses the pending-intent mechanism the alarm skill already uses, rather
    than a second one: chat_service checks for exactly one pending fact
    before it routes anything else, which is the behaviour needed here — the
    answer to "what's your name?" is a bare name, and a bare name matches no
    trigger and would otherwise go to the LLM as small talk.

    Any older pending introduction is cleared first. Two of them queued up
    would mean the second question's answer resolving the first one.
    """
    try:
        from backend.modules.router.chat_service import get_memory
        mem = get_memory()
        for fact in mem.get_facts(category="pending_intent"):
            if fact.get("content") == AWAITING_NAME:
                mem.delete_fact(fact["id"])
        mem.add_fact(
            category="pending_intent",
            content=AWAITING_NAME,
            confidence=1.0,
            source="introductions",
            user=session_id or "camera",
        )
        return True
    except Exception:
        # She has already asked out loud by this point. Failing to arm means
        # the answer is treated as ordinary conversation, which is a poor
        # outcome but not a broken one — never a reason to raise into the
        # perception loop.
        return False
