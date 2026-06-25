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
    """Grab one BGR frame from the local camera (raises on failure)."""
    from backend.core.config import config
    from backend.modules.vision.capture import snapshot
    return snapshot(config.CAMERA_DEVICE)


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    # ── Face enrollment: "remember my face as <name>" ────────────────────────
    from backend.modules.vision import face_id

    enroll_name = face_id.parse_enroll_command(utterance)
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
