"""PA-57 — Wikipedia lookup: "who is Einstein" / "tell me about black holes"."""
from __future__ import annotations
import re
from backend.core.http_client import get as http_get

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

# Topics that are about the speaker, about her, or a matter of opinion —
# there is no article to fetch, and looking one up anyway produces a
# confident miss where a conversation belonged.
_ABOUT_HER = re.compile(
    r"^(?:your|yourself|you|my|myself|me|us|our|"
    r"dein|dich|dir|mein|mich|uns)\b"
    r"|\b(?:favourite|favorite|opinion|think|feel|lieblings)\b",
    re.I,
)


def _first_sentence(text: str) -> str:
    parts = _SENTENCE_END.split(text.strip(), maxsplit=1)
    return parts[0].strip()


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")
    topic = _STRIP.sub("", utterance).strip(" ?.")

    if not topic or len(topic) < 3:
        return None                      # nothing to look up — let the LLM talk

    # "Tell me about yourself", "who is your favourite person" — the trigger
    # fires but there is no encyclopedia article behind it. These are the
    # questions people ask an assistant to see whether it can hold a
    # conversation, and answering them with a Wikipedia miss is the worst
    # possible first impression.
    if _ABOUT_HER.search(topic):
        return None

    # Capitalise first letter — Wikipedia titles are case-sensitive for first char
    topic_title = topic[0].upper() + topic[1:]

    try:
        resp = http_get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic_title}",
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
