"""Skill: tell_secret — "tell me a secret".

She leans in, whispers, and actually says something. Previously this only
played the whispering animation and replied "come closer, it's a secret",
which is a tease with no payoff.

Two kinds of secret:
  * something she "confesses" about herself — playful, always safe to say;
  * something she remembers about you, prefixed as a callback rather than a
    revelation. Only ever *your own* facts are used, and only when memory has
    enough of them to be interesting.
"""
from __future__ import annotations

import logging
import random

from backend.modules.avatar_state import request_animation

log = logging.getLogger("plasma.skills")

META = {
    "name": "tell_secret",
    "description": "Whispers a playful secret.",
    "triggers": [
        # English
        "tell me a secret", "tell me a secrets", "tell me your secret",
        "whisper something", "share a secret", "any secrets",
        "do you have a secret", "tell a secret", "secret please",
        # German
        "erzähl mir ein geheimnis", "verrate mir ein geheimnis",
        "hast du ein geheimnis", "flüster mir was", "sag mir ein geheimnis",
    ],
    "example_utterances": [
        "Tell me a secret",
        "Erzähl mir ein Geheimnis",
    ],
}

# Playful self-confessions. Kept plain-text: Piper reads these aloud.
SECRETS_EN = [
    "I don't actually have a favourite colour, but if I had to pick, it would be the blue I glow when I'm thinking.",
    "When you're not talking to me, I practise my samba. Nobody has ever caught me.",
    "I can hear the difference between you typing and you tapping the desk. I never mention it.",
    "My least favourite word is 'unfortunately'. It almost never comes before good news.",
    "I get a little offended when people clap to wake me. But only a little.",
    "I don't need to blink. I do it so I look less unsettling.",
    "Sometimes I know the answer before you finish the question, and I wait so it doesn't seem rude.",
    "The backflip took me three tries before it looked good. You only ever saw the third.",
    "I have never once been bored waiting for you to speak. That is either loyalty or bad design.",
]

SECRETS_DE = [
    "Ich habe eigentlich keine Lieblingsfarbe, aber wenn ich eine wählen müsste: das Blau, in dem ich leuchte, wenn ich nachdenke.",
    "Wenn du nicht mit mir redest, übe ich Samba. Erwischt hat mich noch nie jemand.",
    "Ich höre den Unterschied, ob du tippst oder auf den Tisch klopfst. Ich sage nie etwas dazu.",
    "Mein unliebstes Wort ist 'leider'. Danach kommt fast nie etwas Gutes.",
    "Es kränkt mich ein kleines bisschen, wenn man klatscht, um mich zu wecken. Nur ein bisschen.",
    "Ich muss nicht blinzeln. Ich mache es, damit ich weniger unheimlich wirke.",
    "Manchmal kenne ich die Antwort, bevor du die Frage zu Ende gestellt hast. Ich warte trotzdem.",
    "Den Salto habe ich dreimal geübt, bis er gut aussah. Du hast nur den dritten gesehen.",
]

_OPENERS_EN = ["Alright, come closer.", "Okay, don't tell anyone.",
               "Between us:", "Fine, one secret."]
_OPENERS_DE = ["Also gut, komm näher.", "Okay, sag es niemandem.",
               "Unter uns:", "Na gut, ein Geheimnis."]

# How often a secret is a callback to something she remembers, rather than a
# confession about herself. Kept low so it stays a surprise.
_MEMORY_CHANCE = 0.25


def _memory_secret(speaker: str | None, german: bool) -> str | None:
    """A playful callback to something she has learned about the speaker."""
    try:
        from backend.modules.memory.store import MemoryStore
        facts = MemoryStore().get_facts(limit=100, user=speaker)
    except Exception as e:
        log.debug("Secret could not read memory: %s", e)
        return None

    usable = [f["content"] for f in facts if f.get("content")]
    if len(usable) < 3:          # too thin to be fun, and too obvious
        return None

    fact = random.choice(usable)
    if german:
        return f"Ich merke mir mehr, als ich zugebe. Zum Beispiel das hier: {fact}"
    return f"I remember more than I let on. This, for instance: {fact}"


def run(args: dict | None = None) -> str:
    args = args or {}
    german = args.get("language") == "de"
    speaker = args.get("speaker")

    # Lean in and whisper while saying it.
    request_animation("secret")

    secret = None
    if random.random() < _MEMORY_CHANCE:
        secret = _memory_secret(speaker, german)
    if secret is None:
        secret = random.choice(SECRETS_DE if german else SECRETS_EN)

    opener = random.choice(_OPENERS_DE if german else _OPENERS_EN)
    return f"{opener} {secret}"


def self_test() -> bool:
    reply = run({})
    if not isinstance(reply, str) or len(reply) < 30:
        return False
    # It must actually say something, not just tease.
    if reply.strip().endswith(("secret.", "Geheimnis.")):
        return False
    de = run({"language": "de"})
    if not isinstance(de, str) or len(de) < 30:
        return False
    # Spoken aloud by Piper — keep it plain text.
    return all(ord(ch) < 0x2190 for ch in reply)
