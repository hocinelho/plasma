"""PA-58 — Translation skill: "say hello in French" / "translate good morning to Spanish"."""
from __future__ import annotations
import re
from backend.core.http_client import get as http_get

META = {
    "name": "translator",
    "description": "Translates a word or phrase into another language.",
    "triggers": [
        "say ",
        "translate ",
        "how do you say ",
        "how do i say ",
        "what is hello in ",
        "what is goodbye in ",
        "in french",
        "in spanish",
        "in german",
        "in italian",
        "in portuguese",
        "in arabic",
        "in chinese",
        "in japanese",
        "in russian",
    ],
}

_LANG_CODES: dict[str, str] = {
    "french": "fr", "spanish": "es", "german": "de", "italian": "it",
    "portuguese": "pt", "arabic": "ar", "chinese": "zh", "japanese": "ja",
    "russian": "ru", "dutch": "nl", "korean": "ko", "hindi": "hi",
    "turkish": "tr", "polish": "pl", "swedish": "sv", "norwegian": "no",
    "danish": "da", "finnish": "fi", "greek": "el", "hebrew": "he",
    "thai": "th", "vietnamese": "vi", "indonesian": "id",
}

# "say <phrase> in <lang>" OR "translate <phrase> to <lang>"
_PATTERN = re.compile(
    r"(?:say|translate|how\s+(?:do\s+you|do\s+i)\s+say)\s+(.+?)\s+(?:in|to)\s+([a-z]+)\b",
    re.I,
)
# "what is <phrase> in <lang>"
_WHAT_PATTERN = re.compile(
    r"what\s+is\s+(.+?)\s+in\s+([a-z]+)\b",
    re.I,
)


def _detect_lang_from_utterance(utterance: str) -> tuple[str, str] | None:
    for pat in (_PATTERN, _WHAT_PATTERN):
        m = pat.search(utterance)
        if m:
            phrase, lang_word = m.group(1).strip(" '\"?."), m.group(2).lower()
            if lang_word in _LANG_CODES:
                return phrase, lang_word
    return None


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")

    parsed = _detect_lang_from_utterance(utterance)
    if not parsed:
        # No target language named, so nothing was asked to be translated.
        # "say " is a trigger because "say hello in French" is the natural
        # phrasing, and it also sits inside "why do you say that".
        return None

    phrase, lang_word = parsed
    lang_code = _LANG_CODES[lang_word]

    try:
        resp = http_get(
            "https://api.mymemory.translated.net/get",
            params={"q": phrase, "langpair": f"en|{lang_code}"},
            headers={"User-Agent": "Plasma-VoiceAssistant/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("responseData", {}).get("translatedText", "")
        if not translated or translated.lower() == phrase.lower():
            return f"Couldn't translate '{phrase}' to {lang_word}."
        return f"'{phrase}' in {lang_word} is '{translated}'."
    except Exception as e:
        if "timeout" in type(e).__name__.lower() or "timeout" in str(e).lower():
            return "The translation service took too long."
        return f"Couldn't reach the translation service: {e}"


def self_test() -> bool:
    # offline-safe: just check parsing
    result = _detect_lang_from_utterance("say hello in French")
    return result is not None and result[0].lower() == "hello" and result[1] == "french"
