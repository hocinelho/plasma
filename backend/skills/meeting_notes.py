"""Skill: meeting notes — record a meeting, then write Word minutes.

  "start the meeting notes"  → begins listening and transcribing
  "stop the meeting"         → stops, summarizes, saves a .docx
  "meeting status"           → how long it has been running

Recording only ever starts on an explicit command and the reply says so out
loud, so nobody in the room is recorded without it being announced.
"""
from __future__ import annotations

import logging
import re

from backend.modules.meeting import export_docx
from backend.modules.meeting.recorder import recorder
from backend.modules.meeting.summarizer import summarize

log = logging.getLogger("plasma.meeting")

META = {
    "name": "meeting_notes",
    "description": "Records a meeting, transcribes it and writes Word minutes.",
    "triggers": [
        # English
        "start meeting", "start the meeting", "start meeting notes",
        "record the meeting", "record this meeting", "take meeting notes",
        "minute this meeting", "start taking notes",
        # "start recording" must be listed explicitly: open_app owns the very
        # generic trigger "start ", and matching is longest-trigger-wins.
        "start recording", "recording the meeting", "record meeting",
        "stop meeting", "stop the meeting", "end the meeting",
        "stop recording", "stop recording the meeting", "finish the meeting",
        "meeting status", "are you recording",
        "summarize the meeting", "summarise the meeting", "meeting summary",
        # German
        "meeting aufnehmen", "besprechung aufnehmen", "protokoll starten",
        "meeting starten", "notizen für das meeting",
        "meeting beenden", "besprechung beenden", "protokoll beenden",
        "meeting stoppen", "meeting zusammenfassen",
        "meeting status", "nimmst du auf",
    ],
    "example_utterances": [
        "Start meeting notes",
        "Stop the meeting and summarize it",
        "Protokoll starten",
    ],
}

_STOP = ["stop", "end", "finish", "beenden", "stoppen", "schluss"]
_STATUS = ["status", "are you recording", "nimmst du auf", "läuft"]
_SUMMARIZE = ["summar", "zusammenfass", "protokoll schreiben"]

# Allow words between the keyword and the preposition, so both
# "start meeting notes about X" and "protokoll starten für X" work.
_TITLE_RE = re.compile(
    r"\b(?:meeting|besprechung|protokoll)\b.*?\b(?:about|on|für|über|zu)\s+(.+)$",
    re.IGNORECASE,
)


def _title_from(utterance: str) -> str:
    m = _TITLE_RE.search(utterance or "")
    if not m:
        return ""
    return re.split(r"[.?!]", m.group(1))[0].strip()


def _finish(german: bool) -> str:
    """Stop recording, summarize, and write the Word file."""
    state = recorder.stop()
    if state is None or not state.segments:
        return ("Ich habe nichts aufgenommen." if german
                else "I didn't capture anything for that meeting.")

    summary = summarize(state.transcript)
    minutes = len(state.segments)

    try:
        path = export_docx.write_minutes(state, summary)
    except RuntimeError as e:
        # Transcript is safe on disk either way — say where, don't just fail.
        log.warning("Word export unavailable: %s", e)
        return (
            f"Das Meeting ist gespeichert ({minutes} Abschnitte), aber das "
            f"Word-Dokument konnte nicht erstellt werden: {e}"
            if german else
            f"The meeting is saved ({minutes} segments), but I couldn't write "
            f"the Word file: {e}"
        )

    if german:
        return (f"Meeting beendet. Ich habe das Protokoll nach {path.name} "
                f"geschrieben — {state.duration_min:.0f} Minuten.")
    return (f"Meeting finished. I wrote the minutes to {path.name} — "
            f"{state.duration_min:.0f} minutes.")


def run(args: dict | None = None) -> str:
    args = args or {}
    utterance = (args.get("utterance") or "").lower()
    german = args.get("language") == "de"

    if any(w in utterance for w in _STATUS) and "start" not in utterance:
        st = recorder.status()
        if not st["recording"]:
            return "Ich nehme gerade nichts auf." if german else "I'm not recording right now."
        return (f"Ich nehme seit {st['duration_min']:.0f} Minuten auf, "
                f"{st['segments']} Abschnitte bisher."
                if german else
                f"Recording for {st['duration_min']:.0f} minutes, "
                f"{st['segments']} segments so far.")

    if any(w in utterance for w in _STOP) or any(w in utterance for w in _SUMMARIZE):
        if not recorder.is_recording:
            return ("Es läuft gerade keine Aufnahme." if german
                    else "No meeting is being recorded at the moment.")
        return _finish(german)

    # Otherwise: start.
    if recorder.is_recording:
        st = recorder.status()
        return (f"Ich nehme schon seit {st['duration_min']:.0f} Minuten auf."
                if german else
                f"I'm already recording — {st['duration_min']:.0f} minutes so far.")

    try:
        state = recorder.start(title=_title_from(args.get("utterance") or ""))
    except RuntimeError as e:
        return str(e)

    if not export_docx.is_available():
        log.warning("python-docx missing — minutes will not be exported.")

    # Say it out loud: everyone present should know recording has begun.
    return (f"Aufnahme läuft: {state.title}. Bitte sag allen Bescheid, dass "
            f"mitgeschrieben wird. Sag 'Meeting beenden', wenn ich das "
            f"Protokoll schreiben soll."
            if german else
            f"Recording now: {state.title}. Please let everyone know the "
            f"meeting is being transcribed. Say 'stop the meeting' when you "
            f"want the minutes.")


def self_test() -> bool:
    # Title extraction, without touching the microphone.
    if _title_from("start meeting notes about the network rollout") != "the network rollout":
        return False
    if _title_from("start meeting notes") != "":
        return False
    # Status must be answerable when nothing is recording.
    reply = run({"utterance": "meeting status"})
    return isinstance(reply, str) and "record" in reply.lower()
