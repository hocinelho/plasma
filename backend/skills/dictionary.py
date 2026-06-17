"""PA-91 — Dictionary skill: "define ephemeral" / "what does resilience mean".

Uses the free Dictionary API (https://api.dictionaryapi.dev) — no key needed.
Returns the part of speech + first definition for the requested word.
"""
from __future__ import annotations
import re

from backend.core.http_client import get as http_get

META = {
    "name": "dictionary",
    "description": "Defines a word using the free Dictionary API.",
    "triggers": [
        "define ",
        "definition of",
        "what does ",
        "what is the meaning of",
        "what is the definition of",
        "meaning of ",
        "look up the word",
        # German triggers (word is still looked up in English)
        "was bedeutet ",
        "was heißt ",
        "definiere ",
        "erkläre das wort",
        "bedeutung von",
    ],
    "example_utterances": [
        "Define ephemeral",
        "What does resilience mean?",
        "What is the definition of serendipity?",
        "Was bedeutet ephemeral?",
    ],
}

# "define X", "what does X mean", "meaning of X", "definition of X"
_WORD_RE = re.compile(
    r"(?:define|definiere)\s+(.+)"
    r"|what\s+does\s+(.+?)\s+mean"
    r"|(?:meaning|definition)\s+of\s+(.+)"
    r"|what\s+is\s+the\s+(?:meaning|definition)\s+of\s+(.+)"
    r"|look\s+up\s+(?:the\s+word\s+)?(.+)"
    r"|was\s+(?:bedeutet|heißt)\s+(.+)"
    r"|bedeutung\s+von\s+(.+)",
    re.I,
)

_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


def _extract_word(utterance: str) -> str | None:
    m = _WORD_RE.search(utterance.strip(" .?!"))
    if not m:
        return None
    word = next((g for g in m.groups() if g), None)
    return word.strip(" .?!").split()[0] if word else None  # one word only


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")

    word = _extract_word(utterance)
    if not word:
        if language == "de":
            return "Welches Wort soll ich nachschlagen? Sag zum Beispiel: Was bedeutet ephemeral?"
        return "Which word should I define? Try: 'define ephemeral' or 'what does serendipity mean'."

    try:
        resp = http_get(_API.format(word=word.lower()))
        if resp.status_code == 404:
            if language == "de":
                return f"Ich konnte '{word}' nicht finden."
            return f"I couldn't find a definition for '{word}'."
        resp.raise_for_status()
        entries = resp.json()
        if not entries or not isinstance(entries, list):
            if language == "de":
                return f"Keine Definition für '{word}' gefunden."
            return f"No definition found for '{word}'."

        meanings = entries[0].get("meanings", [])
        if not meanings:
            return f"No definition found for '{word}'."

        first_meaning = meanings[0]
        pos = first_meaning.get("partOfSpeech", "")
        definitions = first_meaning.get("definitions", [])
        definition = definitions[0].get("definition", "") if definitions else ""

        if not definition:
            return f"No definition found for '{word}'."

        if language == "de":
            pos_str = f" ({pos})" if pos else ""
            return f"{word}{pos_str}: {definition}"
        return f"{word} ({pos}): {definition}" if pos else f"{word}: {definition}"

    except Exception as e:
        if language == "de":
            return f"Ich konnte das Wörterbuch nicht erreichen: {e}"
        return f"Couldn't reach the dictionary: {e}"


def self_test() -> bool:
    return _extract_word("define ephemeral") == "ephemeral"
