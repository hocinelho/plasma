"""See-me skill — Plasma looks at you through the camera and reports what it sees.

Answers voice questions about your face and hands using MediaPipe perception
(expression: happy / sleepy / winking; hands: finger count + gestures) plus
optional DeepFace identity ("who am I" by face).

Also handles camera-driven face enrollment:
    "remember my face as Hocine"  →  saves a face crop for future recognition.

All vision runs server-side on a single fresh snapshot, so it works the same
whether you're at the PC or (later) on a phone hitting the browser UI.
"""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path

log = logging.getLogger("plasma.skill.vision_query")

META = {
    "name": "vision_query",
    "description": "Looks through the camera and reports your expression, hand gestures, finger count, or face identity.",
    "triggers": [
        # English — hands
        "how many fingers",
        "count my fingers",
        "what gesture",
        "what am i doing",
        # English — face / expression
        "how do i look",
        "do i look",
        "am i smiling",
        "am i happy",
        "am i sleepy",
        "am i tired",
        "what do you see on my face",
        # English — presence / face identity / enrollment
        "do you see me",
        "can you see me",
        "do you recognize my face",
        "do you recognise my face",
        "remember my face",
        "learn my face",
        "memorize my face",
        "memorise my face",
        "save my face",
        "register my face",
        "remember me",
        # German
        "wie viele finger",
        "zähl meine finger",
        "welche geste",
        "wie sehe ich aus",
        "lächle ich",
        "bin ich müde",
        "siehst du mich",
        "erkennst du mein gesicht",
        "merke dir mein gesicht",
    ],
    "example_utterances": [
        "How many fingers am I holding up?",
        "How do I look?",
        "Do you see me?",
        "Remember my face as Hocine",
        "Wie viele Finger?",
    ],
}


def _capture():
    """Grab one BGR frame of what she can see (raises on failure).

    snapshot() prefers whatever the browser is already streaming, so when the
    overlay is watching this costs nothing at all — see capture.snapshot.
    """
    from backend.core.config import config
    from backend.modules.vision.capture import snapshot
    return snapshot(config.CAMERA_DEVICE)


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    from backend.modules.vision import face_id

    # ── Answering "what's your name?" ────────────────────────────────────────
    # She saw a face she did not know and asked. The reply is routed straight
    # back here (chat_service's pending-intent path), and it is just a name —
    # there is nothing in "Hocine" to route on, which is exactly why the
    # pending state has to say what question it is an answer to.
    from backend.modules.vision.introductions import AWAITING_NAME

    if (args or {}).get("pending") == AWAITING_NAME:
        offered = face_id.parse_offered_name(utterance)
        if not offered:
            # Not a name — a refusal, or she misheard. Say nothing more about
            # it: pressing a stranger twice for their name is worse than not
            # learning it. The pending state is already consumed, so the next
            # thing they say is an ordinary conversation again.
            return ("Kein Problem." if de else "No problem.")
        try:
            frame = _capture()
        except Exception as e:
            return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"
        face_id.enroll(offered, frame)
        return (f"Freut mich, {offered}! Ich merke mir dein Gesicht."
                if de else
                f"Nice to meet you, {offered}! I'll remember your face.")

    # ── Face enrollment: "remember my face as <name>" ────────────────────────
    enroll_name = face_id.parse_enroll_command(utterance)
    # "memorize my face" with no name → use the identified speaker, else ask.
    if not enroll_name and face_id.is_enroll_intent(utterance):
        enroll_name = (args or {}).get("speaker")
        if not enroll_name:
            return (
                "Wie soll ich dein Gesicht nennen? Sag z.B. 'Merke dir mein Gesicht als Hocine'."
                if de
                else "What name should I save your face under? Say 'remember my face as <your name>'."
            )
    if enroll_name:
        try:
            frame = _capture()
        except Exception as e:
            return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"
        return face_id.enroll(enroll_name, frame)

    # ── Capture a frame for perception ───────────────────────────────────────
    try:
        frame = _capture()
    except ImportError as e:
        return (
            f"Kamera-Pakete fehlen ({e}). Installiere: pip install opencv-python"
            if de
            else f"Camera packages missing ({e}). Install: pip install opencv-python"
        )
    except Exception as e:
        return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"

    # ── Run MediaPipe perception ─────────────────────────────────────────────
    try:
        from backend.modules.vision.perception import get_perceiver, summarize
        perception = get_perceiver().perceive(frame)
    except ImportError:
        return (
            "Gesichts-/Handerkennung fehlt. Installiere: pip install mediapipe"
            if de
            else "Face/hand perception isn't installed. Run: pip install mediapipe"
        )
    except Exception as e:
        log.warning("vision_query: perception failed: %s", e)
        return f"Ich konnte nicht klar sehen: {e}" if de else f"I couldn't see clearly: {e}"

    summary = summarize(perception, de)

    # ── Add face identity when the user asks "who/recognize" ─────────────────
    lower = utterance.lower()
    wants_identity = any(
        w in lower for w in ("recogn", "who", "erkennst", "wer")
    )
    if wants_identity and perception.get("faces"):
        try:
            name, _dist = face_id.identify(frame)
        except Exception:
            name = None
        if name:
            prefix = f"Du bist {name}. " if de else f"You're {name}. "
            return prefix + summary
        if face_id.is_available():
            return (
                "Ich erkenne dein Gesicht noch nicht. Sag: merke dir mein Gesicht als, und deinen Namen. "
                if de
                else "I don't recognize your face yet. Say 'remember my face as' and your name. "
            ) + summary

    return summary


def self_test() -> bool:
    # Pure-logic smoke test — no camera needed.
    from backend.modules.vision.perception import summarize
    out = summarize({"faces": [{"expression": "happy", "wink": None}], "hands": []}, de=False)
    return isinstance(out, str) and "happy" in out.lower()
