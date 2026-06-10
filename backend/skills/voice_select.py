"""PA-67 — Voice selection skill: "switch voice to thorsten" / "list voices"."""
from __future__ import annotations
import re

META = {
    "name": "voice_select",
    "description": "Lists available TTS voices and switches between them.",
    "triggers": [
        "switch voice to",
        "change voice to",
        "change your voice to",
        "use the voice",
        "use voice",
        "list voices",
        "what voices",
        "which voices",
        "available voices",
        "reset voice",
        "default voice",
        "wechsle die stimme zu",
        "stimme wechseln",
        "welche stimmen",
    ],
    "example_utterances": [
        "Switch voice to thorsten",
        "List voices",
        "Reset voice",
    ],
}

_SWITCH_RE = re.compile(
    r"(?:switch|change|use)\s+(?:the\s+|your\s+)?voice\s+(?:to\s+)?([a-zA-Z][\w\-]*)"
    r"|wechsle\s+die\s+stimme\s+zu\s+([a-zA-Z][\w\-]*)",
    re.IGNORECASE,
)
_LIST_RE = re.compile(r"\b(?:list|what|which|available|welche)\b.*\bvoices?\b|stimmen", re.IGNORECASE)
_RESET_RE = re.compile(r"\b(?:reset|default|normal)\s+voice\b", re.IGNORECASE)


def _short_name(filename: str) -> str:
    """de_DE-thorsten-medium.onnx → thorsten"""
    stem = filename.replace(".onnx", "")
    parts = stem.split("-")
    return parts[1] if len(parts) >= 2 else stem


def run(args: dict | None = None) -> str:
    from backend.modules.voice import tts

    utterance = ((args or {}).get("utterance") or "").strip()
    voices = tts.list_available_voices()

    if _RESET_RE.search(utterance):
        tts.set_voice_override(None)
        return "Okay, back to my default voice."

    m = _SWITCH_RE.search(utterance)
    if m:
        wanted = (m.group(1) or m.group(2) or "").lower()
        if not voices:
            return "I don't have any extra voices installed. Download voice models into the voices folder first."
        for fname in voices:
            if wanted in fname.lower():
                try:
                    name = tts.set_voice_override(tts.VOICES_DIR / fname)
                    return f"Switched to the {name} voice. How do I sound?"
                except Exception as e:
                    return f"I couldn't load that voice: {e}"
        names = ", ".join(sorted({_short_name(v) for v in voices}))
        return f"I don't have a voice called {wanted}. Available: {names}."

    if _LIST_RE.search(utterance) or not m:
        if not voices:
            return "Only my default voice is installed. Download more Piper voices into the voices folder."
        names = ", ".join(sorted({_short_name(v) for v in voices}))
        current = tts.get_voice_override_name()
        suffix = f" Currently using: {current}." if current else " Currently using the default voice."
        return f"Available voices: {names}.{suffix}"

    return "Say 'switch voice to' followed by a voice name, or 'list voices'."


def self_test() -> bool:
    return _SWITCH_RE.search("switch voice to thorsten") is not None
