"""PA-65 — Who am I: reports the identified speaker and enrolled profiles."""
from __future__ import annotations

META = {
    "name": "who_am_i",
    "description": "Tells the user who Plasma thinks is speaking (speaker ID).",
    "triggers": [
        "who am i",
        "do you know who i am",
        "do you recognize me",
        "do you recognise me",
        "whose voice is this",
        "wer bin ich",
        "erkennst du mich",
    ],
    "example_utterances": ["Who am I?", "Do you recognize me?"],
}


def run(args: dict | None = None) -> str:
    from backend.modules.voice import speaker_id

    speaker = (args or {}).get("speaker")
    language = (args or {}).get("language", "en")

    if speaker:
        if language == "de":
            return f"Du bist {speaker}. Ich erkenne deine Stimme."
        return f"You're {speaker}. I recognize your voice."

    if not speaker_id.is_available():
        return (
            "Speaker identification isn't installed. "
            "Run: pip install resemblyzer — then say 'remember my voice as' and your name."
        )

    enrolled = speaker_id.list_speakers()
    if not enrolled:
        if language == "de":
            return "Ich kenne deine Stimme noch nicht. Sag: merke dir meine Stimme als, und deinen Namen."
        return "I don't know your voice yet. Say 'remember my voice as' followed by your name."

    if language == "de":
        return "Ich bin nicht sicher. Ich kenne: " + ", ".join(enrolled) + "."
    return "I'm not sure. Voices I know: " + ", ".join(enrolled) + "."


def self_test() -> bool:
    return isinstance(run({"speaker": "Tester"}), str)
