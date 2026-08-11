"""Makes the on-screen avatar move — waves, nods, shrugs, thumbs up…

The skill returns the *spoken* reply; the actual movement is passed to the
browser out-of-band: `run()` records the requested gesture and `backend/main.py`
pops it and ships it in the chat response as `gesture`. The frontend
(frontend/avatar.js) plays it on the 3D avatar.

The queued gesture lives in `backend.modules.avatar_state`, NOT in this module:
the skill registry imports skill files under a synthetic module name, so this
file's globals are a different object from the `backend.skills.avatar_move` that
main.py imports. Shared state has to sit somewhere both reach normally.

Only gestures the avatar renderer actually knows are ever recorded — see
GESTURES below, which mirrors TalkingHead's gestureTemplates + animated emojis.
"""
from __future__ import annotations

import random

from backend.modules.avatar_state import pop_gesture, request_gesture

META = {
    "name": "avatar_move",
    "description": "Makes the avatar move — wave, nod, shake head, shrug, thumbs up, point.",
    "triggers": [
        # English
        "wave", "wave at me", "say hi", "say hello",
        "move", "can you move", "do some movement", "move something",
        "nod", "shake your head", "shrug", "thumbs up", "thumbs down",
        "point at", "show me a gesture", "do a gesture", "raise your hand",
        "dance", "can you walk", "walk", "jump", "run around", "turn around",
        # German
        "winke", "winken", "wink mal", "beweg dich", "bewegung",
        "nicke", "nicken", "kopfschütteln", "schulterzucken",
        "daumen hoch", "daumen runter", "zeig mir eine geste", "tanz",
    ],
    "example_utterances": [
        "Can you wave at me?",
        "Do some movement",
        "Wink mal!",
        "Give me a thumbs up",
    ],
}

# Gesture name → (English reply, German reply). Names must exist in the
# renderer's gesture set (hand gestures + animated emojis).
# Replies are spoken by TTS, so keep them plain text — no emoji.
GESTURES = {
    "handup":    ("Waving at you!", "Ich winke dir!"),
    "thumbup":   ("Thumbs up!", "Daumen hoch!"),
    "thumbdown": ("Thumbs down.", "Daumen runter."),
    "ok":        ("Got it.", "Alles klar."),
    "index":     ("Pointing.", "Ich zeige."),
    "shrug":     ("No idea!", "Keine Ahnung!"),
    "namaste":   ("Namaste.", "Namaste."),
    "side":      ("Here's a relaxed pose.", "Eine entspannte Haltung."),
    "yes":       ("Nodding yes.", "Ich nicke."),
    "no":        ("Shaking my head.", "Ich schüttle den Kopf."),
}

# Replies for the "just move somehow" case, where the specific gesture is
# arbitrary and a gesture-specific line ("No idea!") would make no sense.
_SURPRISE_REPLIES = [
    ("Here you go!", "Bitte schön!"),
    ("Watch this!", "Schau mal!"),
    ("How's this?", "Wie ist das?"),
]

# Whole-body motion needs animation clips that aren't installed yet. Say so
# plainly instead of letting the model invent a walk it can't perform.
UNSUPPORTED = [
    "walk", "walking", "jump", "jumping", "run", "running", "dance", "dancing",
    "turn around", "sit down", "stand up", "spin",
    "lauf", "laufen", "geh", "gehen", "spring", "springen", "tanz", "tanzen",
    "dreh dich", "setz dich",
]
_UNSUPPORTED_REPLY = (
    "I can't walk or dance yet — that needs full-body animations. "
    "But I can wave, nod, shrug, point or give you a thumbs up.",
    "Laufen oder tanzen kann ich noch nicht — dafür fehlen mir die "
    "Ganzkörper-Animationen. Winken, nicken, Schultern zucken, zeigen oder "
    "Daumen hoch geht aber.",
)

# Phrase → gesture. Checked longest-first so "thumbs down" beats "thumbs".
KEYWORDS = {
    "handup": ["wave", "waving", "say hi", "say hello", "raise your hand",
               "hand up", "wink", "winke", "winken", "hallo sagen"],
    "thumbdown": ["thumbs down", "thumb down", "daumen runter", "daumen nach unten"],
    "thumbup": ["thumbs up", "thumb up", "daumen hoch", "daumen nach oben",
                "well done", "good job", "gut gemacht"],
    "ok": ["ok sign", "okay sign", "ok gesture", "okay geste"],
    "index": ["point", "pointing", "zeig", "zeigen", "finger"],
    "shrug": ["shrug", "schulterzucken", "zuck", "no idea", "keine ahnung"],
    "namaste": ["namaste", "bow", "verbeug"],
    "yes": ["nod", "nicke", "nicken", "say yes", "ja sagen"],
    "no": ["shake your head", "shake head", "kopfschütteln", "kopf schütteln",
           "say no", "nein sagen"],
}

# When the user just says "move" / "dance" / "do something", pick from these.
_SURPRISE = ["handup", "thumbup", "ok", "index", "shrug", "namaste"]

def pop_last_gesture(max_age_s: float = 30.0) -> str | None:
    """Return (once) the most recently requested gesture if it's still fresh.

    Thin wrapper over the shared store so callers can use either entry point.
    """
    return pop_gesture(max_age_s)


def _pick(utterance: str) -> tuple[str, bool]:
    """Map an utterance to a gesture. Returns (name, was_specifically_asked)."""
    text = (utterance or "").lower()
    # Longest phrases first so specific beats generic.
    matches = [
        (len(phrase), gesture)
        for gesture, phrases in KEYWORDS.items()
        for phrase in phrases
        if phrase in text
    ]
    if matches:
        return max(matches)[1], True
    return random.choice(_SURPRISE), False


def run(args: dict | None = None) -> str:
    args = args or {}
    utterance = args.get("utterance", "")
    german_wanted = args.get("language") == "de"

    text = utterance.lower()
    specific_match = any(
        phrase in text for phrases in KEYWORDS.values() for phrase in phrases
    )
    # "Can you walk?" — be honest, unless they also named something we CAN do.
    if not specific_match and any(word in text for word in UNSUPPORTED):
        return _UNSUPPORTED_REPLY[1 if german_wanted else 0]

    gesture, specific = _pick(utterance)
    request_gesture(gesture)
    english, german = GESTURES[gesture] if specific else random.choice(_SURPRISE_REPLIES)
    return german if german_wanted else english


def self_test() -> bool:
    # Explicit keyword wins over the random fallback.
    if run({"utterance": "can you wave at me"}) != GESTURES["handup"][0]:
        return False
    if pop_last_gesture() != "handup":
        return False
    # A gesture is only popped once.
    if pop_last_gesture() is not None:
        return False
    # Longest-match: "thumbs down" must not be read as "thumbs up".
    run({"utterance": "give me a thumbs down"})
    if pop_last_gesture() != "thumbdown":
        return False
    # German replies, and a bare "move" still picks something valid.
    if run({"utterance": "winke mal", "language": "de"}) != GESTURES["handup"][1]:
        return False
    reply = run({"utterance": "do some movement"})
    if pop_last_gesture() not in _SURPRISE:
        return False
    # The generic case must not borrow a gesture-specific line.
    if reply not in [en for en, _ in _SURPRISE_REPLIES]:
        return False
    # Spoken replies must stay plain text (TTS reads them aloud).
    return all(t.isascii() or "ü" in t or "ö" in t or "ä" in t or "ß" in t
               for pair in GESTURES.values() for t in pair)
