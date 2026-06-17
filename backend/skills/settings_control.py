"""Skill: settings_control — change runtime settings by voice (PA-64).

Lets the user switch Whisper model, language, and query current settings.
Changes are runtime-only — they reset on restart.
"""
from __future__ import annotations
import logging
import re

log = logging.getLogger("plasma.skill.settings_control")

META = {
    "name": "settings_control",
    "description": "Change Whisper model or language settings by voice.",
    "triggers": [
        # Model switching
        "switch to faster model",
        "use a faster model",
        "switch to accurate model",
        "use accurate model",
        "switch to better model",
        "switch to default model",
        "reset model",
        # Model query
        "what model are you using",
        "current model",
        "which model",
        # Language switching
        "switch language to",
        "speak english",
        "speak german",
        "sprich deutsch",
        "auto detect language",
        "detect language automatically",
        # Language query
        "what language",
        "which language",
        # German variants
        "wechsle zum schnelleren modell",
        "schnelleres modell",
        "wechsle zum besseren modell",
        "welches modell",
        "sprache wechseln",
        "welche sprache",
        "sprache auf englisch",
        "sprache auf deutsch",
        "automatische sprache",
    ],
    "example_utterances": [
        "Switch to a faster model",
        "Use accurate model",
        "What model are you using?",
        "Switch language to German",
        "Speak English",
        "Auto detect language",
        "What language are you using?",
        "Wechsle zum schnelleren Modell",
        "Sprich Deutsch",
        "Welches Modell?",
    ],
}

# Model presets
_MODEL_FAST = "tiny.en"
_MODEL_DEFAULT = "small"
_MODEL_ACCURATE = "medium"

# Language map (spoken name -> whisper code)
_LANGUAGES = {
    "english": "en",
    "englisch": "en",
    "german": "de",
    "deutsch": "de",
    "french": "fr",
    "französisch": "fr",
    "spanish": "es",
    "spanisch": "es",
}


def _reload_whisper(new_model: str) -> None:
    """Reload the Whisper ASR singleton with a new model."""
    try:
        from backend.modules.voice import pipeline
        pipeline.reload_model(new_model)
    except Exception as e:
        log.warning(f"Whisper reload failed (will use new model on next cold start): {e}")


def run(args: dict | None = None) -> str:
    from backend.core.config import config

    utterance = ((args or {}).get("utterance") or "").lower().strip()
    suffix = " This change lasts until you restart Plasma."

    # ── Model switching ───────────────────────────────────────
    if _matches_any(utterance, [
        "faster model", "schnelleres modell", "schnelleren modell",
    ]):
        old = config.WHISPER_MODEL
        config.WHISPER_MODEL = _MODEL_FAST
        _reload_whisper(_MODEL_FAST)
        return f"Switched from {old} to {_MODEL_FAST} — faster but English only.{suffix}"

    if _matches_any(utterance, [
        "accurate model", "better model", "besseren modell", "besseres modell",
    ]):
        old = config.WHISPER_MODEL
        config.WHISPER_MODEL = _MODEL_ACCURATE
        _reload_whisper(_MODEL_ACCURATE)
        return f"Switched from {old} to {_MODEL_ACCURATE} — most accurate, multilingual.{suffix}"

    if _matches_any(utterance, [
        "default model", "reset model", "standard modell",
    ]):
        old = config.WHISPER_MODEL
        config.WHISPER_MODEL = _MODEL_DEFAULT
        _reload_whisper(_MODEL_DEFAULT)
        return f"Switched from {old} to {_MODEL_DEFAULT} — balanced speed and accuracy.{suffix}"

    # ── Model query ───────────────────────────────────────────
    if _matches_any(utterance, [
        "what model", "which model", "current model", "welches modell",
    ]):
        model = config.WHISPER_MODEL
        is_en = model.endswith(".en")
        kind = "English-only" if is_en else "multilingual"
        return f"I'm using the {model} model ({kind})."

    # ── Language switching ────────────────────────────────────
    if _matches_any(utterance, [
        "auto detect", "detect language automatically",
        "automatische sprache", "automatisch erkennen",
    ]):
        config.WHISPER_LANGUAGE = "auto"
        return f"Now using automatic language detection.{suffix}"

    # "switch language to X" / "speak X" / "sprich deutsch"
    lang_match = re.search(
        r"(?:switch language to|speak|sprache auf|sprich)\s+(\w+)",
        utterance,
    )
    if lang_match:
        spoken = lang_match.group(1).strip()
        code = _LANGUAGES.get(spoken)
        if code:
            config.WHISPER_LANGUAGE = code
            return f"Language set to {spoken} ({code}).{suffix}"
        return f"I don't know the language '{spoken}'. I support: {', '.join(sorted(set(_LANGUAGES.values())))}."

    if _matches_any(utterance, ["sprache wechseln"]):
        return "Which language? Say 'speak English', 'speak German', or 'auto detect language'."

    # ── Language query ────────────────────────────────────────
    if _matches_any(utterance, [
        "what language", "which language", "welche sprache",
    ]):
        lang = config.WHISPER_LANGUAGE
        if lang == "auto":
            return "I'm using automatic language detection."
        return f"I'm listening in {lang}."

    return "I didn't understand that settings command. Try 'switch to faster model', 'speak German', or 'what model are you using'."


def _matches_any(text: str, phrases: list[str]) -> bool:
    return any(p in text for p in phrases)


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
