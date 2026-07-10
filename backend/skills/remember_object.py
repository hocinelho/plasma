"""Teach Plasma a specific object: "remember this as my keys".

Captures a frame from the local camera, crops to the most prominent detected
object (so the embedding is of the item, not the whole room), and enrolls it via
object_memory. Later "find my keys" pins that exact item.
"""
from __future__ import annotations

import logging

log = logging.getLogger("plasma.skill.remember_object")

META = {
    "name": "remember_object",
    "description": "Memorise a specific personal object shown to the camera.",
    "triggers": [
        # English — unambiguous enroll phrasings (avoid bare "this is my …"
        # so we don't collide with face enrollment).
        "remember this as",
        "remember this object",
        "save this as",
        "save this object",
        "learn this object",
        "memorize this as",
        "memorise this as",
        # German
        "merke dir das als",
        "merk dir das als",
        "speichere das als",
    ],
    "example_utterances": [
        "Remember this as my keys",
        "Save this as my wallet",
        "Merke dir das als meine Brille",
    ],
}


def _biggest_box(frame) -> list | None:
    """Return the largest detected object's box, to crop the item being held."""
    try:
        from backend.modules.vision.detector import get_detector
        dets = get_detector().detect(frame)
    except Exception:
        return None
    if not dets:
        return None
    return max(dets, key=lambda d: d["box"][2] * d["box"][3]).get("box")


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    de = (args or {}).get("language", "en") == "de"

    from backend.modules.vision import object_memory

    name = object_memory.parse_enroll_command(utterance)
    if not name:
        return (
            "Was soll ich mir merken? Sag z.B. 'Merke dir das als meine Schlüssel'."
            if de
            else "What should I remember? Try 'remember this as my keys'."
        )

    if not object_memory.is_available():
        return (
            "Objekt-Gedächtnis braucht MediaPipe. Installiere: pip install mediapipe opencv-python"
            if de
            else "Object memory needs MediaPipe. Install: pip install mediapipe opencv-python"
        )

    try:
        from backend.core.config import config
        from backend.modules.vision.capture import snapshot
        frame = snapshot(config.CAMERA_DEVICE)
    except ImportError as e:
        return (
            f"Kamera-Pakete fehlen ({e})." if de else f"Camera packages missing ({e})."
        )
    except Exception as e:
        return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"

    box = _biggest_box(frame)   # crop to the item if we can spot one
    return object_memory.enroll(name, frame, box)


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
