"""Vision skill — camera-based object detection and presence monitoring.

Requires (both optional — skill degrades gracefully if absent):
  pip install mediapipe        # Apache 2.0
  pip install opencv-python    # BSD / Apache 2.0

Actions:
  "what do you see?"          → capture one frame, detect objects, speak result
  "watch for a person"        → start VisionMonitor, fire alert when spotted
  "stop watching"             → stop VisionMonitor
"""
from __future__ import annotations
import logging
import re

log = logging.getLogger("plasma.skill.vision")

# Module-level import so vision_monitor is patchable in tests
from backend.modules.vision.monitor import vision_monitor  # noqa: E402

META = {
    "name": "vision",
    "description": "Use the camera to identify objects or monitor for presence.",
    "triggers": [
        # Snapshot — English
        "what do you see",
        "what can you see",
        "what's in front",
        "look around",
        "describe what you see",
        "scan the room",
        "look at the camera",
        "take a look",
        # Monitor — English
        "watch for",
        "monitor for",
        "alert me when",
        "tell me when you see",
        "keep an eye out for",
        "look out for",
        # Stop — English
        "stop watching",
        "stop monitoring",
        "stop the camera",
        "disable camera",
        # Snapshot — German
        "was siehst du",
        "was kannst du sehen",
        "schau dich um",
        "was ist da",
        "beschreibe was du siehst",
        # Monitor — German
        "halte ausschau nach",
        "beobachte",
        "meld dich wenn du siehst",
        # Stop — German
        "hör auf zu beobachten",
        "kamera deaktivieren",
        "beobachtung stoppen",
    ],
    "example_utterances": [
        "What do you see?",
        "Watch for a person",
        "Stop watching",
        "Was siehst du?",
        "Halte Ausschau nach einer Person",
    ],
}

_STOP_RE = re.compile(
    r"\b(stop (watching|monitoring|camera)|disable camera|"
    r"hör auf zu beobachten|kamera deaktivieren|beobachtung stoppen)\b",
    re.I,
)
_WATCH_RE = re.compile(
    r"\b(?:watch|monitor|alert.*when|tell me when you see|keep an eye out for|look out for"
    r"|halte ausschau nach|beobachte|meld dich wenn du siehst)\s+(?:for\s+)?(?:a\s+|an\s+|einer?\s+)?(.+?)(?:[.?!]|$)",
    re.I,
)


def _detect_from_local_camera() -> list[dict]:
    from backend.core.config import config
    from backend.modules.vision.detector import get_detector
    from backend.modules.vision.capture import snapshot
    frame = snapshot(config.CAMERA_DEVICE)
    return get_detector().detect(frame)


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    session_id = (args or {}).get("session_id", "default")
    de = language == "de"

    # Stop watching
    if _STOP_RE.search(utterance):
        try:
            vision_monitor.stop_watching()
        except Exception as e:
            log.warning("stop_watching failed: %s", e)
        return "Beobachtung gestoppt." if de else "Stopped watching."

    # Watch for something
    m = _WATCH_RE.search(utterance)
    if m:
        target = m.group(1).strip().rstrip(".,!?").lower()
        if not target:
            target = "person"
        try:
            vision_monitor.start_watching(session_id, language, [target])
            return (
                f"Ich halte Ausschau nach '{target}' und melde mich, wenn ich es sehe."
                if de
                else f"Watching for '{target}'. I'll alert you when spotted."
            )
        except Exception as e:
            log.warning("start_watching failed: %s", e)
            return (
                f"Kamera nicht verfügbar: {e}"
                if de
                else f"Camera not available: {e}"
            )

    # Snapshot: "what do you see?"
    try:
        detections = _detect_from_local_camera()
    except ImportError as e:
        install_hint = "pip install mediapipe opencv-python"
        return (
            f"Vision-Pakete fehlen ({e}). Installiere: {install_hint}"
            if de
            else f"Vision packages missing ({e}). Install: {install_hint}"
        )
    except RuntimeError as e:
        return (
            f"Kamera nicht verfügbar: {e}"
            if de
            else f"Camera not available: {e}"
        )
    except Exception as e:
        return (
            f"Kamera-Fehler: {e}"
            if de
            else f"Camera error: {e}"
        )

    if not detections:
        return "Ich erkenne nichts Bestimmtes." if de else "I don't see anything recognizable."

    labels = [f"{d['label']} ({d['score']:.0%})" for d in detections[:5]]
    listed = ", ".join(labels)
    return f"Ich sehe: {listed}." if de else f"I can see: {listed}."


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
