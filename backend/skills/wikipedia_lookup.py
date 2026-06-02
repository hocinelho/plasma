"""PA-57 — Wikipedia lookup: "who is Einstein" / "tell me about black holes"."""
from __future__ import annotations
import re
import httpx

META = {
    "name": "wikipedia_lookup",
    "description": "Fetches a one-sentence Wikipedia summary for a person or topic.",
    "triggers": [
        "who is ",
        "who was ",
        "who invented ",
        "who discovered ",
        "who created ",
        "who founded ",
        "tell me about ",
        "look up ",
        "wikipedia ",
        "what is the history of",
        "who were ",
    ],
}

_STRIP = re.compile(
    r"^(who\s+(?:is|was|invented|discovered|created|founded|were)|"
    r"tell\s+me\s+about|look\s+up|wikipedia|what\s+is\s+the\s+history\s+of)\s*",
    re.I,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _first_sentence(text: str) -> str:
    parts = _SENTENCE_END.split(text.strip(), maxsplit=1)
    return parts[0].strip()


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")
    topic = _STRIP.sub("", utterance).strip(" ?.")

    if not topic:
        return "What would you like me to look up?"

    # Capitalise first letter — Wikipedia titles are case-sensitive for first char
    topic_title = topic[0].upper() + topic[1:]

    try:
        resp = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{httpx.URL(topic_title)}",
            timeout=6.0,
            headers={"User-Agent": "Plasma-VoiceAssistant/1.0"},
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return f"I couldn't find a Wikipedia article for '{topic}'."
        resp.raise_for_status()
        data = resp.json()
        extract = data.get("extract", "")
        if not extract:
            return f"Wikipedia has an article on '{topic}' but no summary."
        return _first_sentence(extract)
    except httpx.TimeoutException:
        return "Wikipedia took too long to respond."
    except Exception as e:
        return f"Couldn't reach Wikipedia: {e}"


def self_test() -> bool:
    # offline-safe: just check parsing works
    from backend.skills.wikipedia_lookup import _first_sentence
    s = _first_sentence("Albert Einstein was a physicist. He developed relativity.")
    return s == "Albert Einstein was a physicist."
