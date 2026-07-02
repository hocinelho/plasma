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
        # Open-vocabulary recognition — "what IS this" (any object)
        "what is this",
        "what's this",
        "what am i holding",
        "what's in my hand",
        "what is in my hand",
        "recognize this",
        "identify this",
        "what object is this",
        # Appearance — "what am I wearing", describe the person
        "what am i wearing",
        "what color is my",
        "what colour is my",
        "describe me",
        "what do i look like",
        "how many people",
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
        "was ist das",
        "was halte ich",
        "was ist das hier",
        "erkenne das",
        "was trage ich",
        "was habe ich an",
        "welche farbe hat mein",
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


# Utterances about the user's appearance get a person-focused prompt.
_APPEARANCE_RE = re.compile(
    r"\b(wear|wearing|what do i look|describe me|colou?r is my|"
    r"trage|anhabe|habe ich an|farbe hat mein|wie sehe ich)\b",
    re.IGNORECASE,
)
_APPEARANCE_PROMPT_EN = (
    "Look at the person in this webcam image. Describe ONLY what is clearly "
    "visible: their clothing and its real colours, and any accessories they are "
    "wearing such as a watch, glasses, hat, or jewellery, plus anything held in "
    "the hand. Do not guess colours you cannot clearly see, and do not describe "
    "the inside or contents of any cup or container. If unsure about something, "
    "leave it out. One or two sentences."
)
_APPEARANCE_PROMPT_DE = (
    "Sieh dir die Person im Webcam-Bild an. Beschreibe NUR, was klar sichtbar "
    "ist: Kleidung und ihre echten Farben sowie Accessoires wie Uhr, Brille, "
    "Hut oder Schmuck und was in der Hand gehalten wird. Rate keine Farben, die "
    "du nicht klar siehst, und beschreibe nicht den Inhalt von Tassen oder "
    "Behältern. Bei Unsicherheit weglassen. Ein bis zwei Sätze."
)


def _vlm_configured() -> bool:
    """True if a vision LLM (Ollama or cloud) is set up for recognition."""
    try:
        from backend.skills import locate as _locate
        return _locate._ollama_vision_available() or _locate._cloud_vision_available()
    except Exception:
        return False


def _recognize_open_vocab(de: bool, utterance: str = "") -> str | None:
    """Open-vocabulary recognition via the vision LLM (names ANY object).

    Best-effort: returns None on any failure (no VLM, no camera, no cv2) so the
    caller falls back to the on-board 80-class detector. Appearance questions
    ("what am I wearing") get a person-focused prompt.
    """
    try:
        import cv2
        import tempfile
        from backend.core.config import config
        from backend.modules.vision.capture import snapshot, apply_gray_world
        from backend.skills import locate as _locate

        prompt = None
        if _APPEARANCE_RE.search(utterance or ""):
            prompt = _APPEARANCE_PROMPT_DE if de else _APPEARANCE_PROMPT_EN

        frame = snapshot(config.CAMERA_DEVICE)
        # Camera settling handles colour at the source; only apply software
        # white-balance if the user explicitly enabled it (it can over-correct).
        if getattr(config, "CAMERA_AUTO_WHITE_BALANCE", False):
            frame = apply_gray_world(frame)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            path = tf.name
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return _locate.describe_scene(path, de, prompt=prompt)
    except Exception as e:
        log.debug("vision: open-vocab recognition unavailable: %s", e)
        return None


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

    # Snapshot: "what do you see / what is this / what am I wearing?"
    # 1) Try open-vocabulary recognition via the vision LLM — names ANY object.
    #    Best-effort; falls through to the detector if no VLM is configured.
    description = _recognize_open_vocab(de, utterance)
    if description:
        return description

    # If a vision LLM IS configured but returned nothing, it errored (often the
    # model is too big for this machine → Ollama 500). Say so instead of the
    # misleading "I don't see anything".
    if _vlm_configured():
        return (
            "Mein Bildmodell hat nicht geantwortet — es ist evtl. zu groß für "
            "diesen Rechner. Versuch ein kleineres: setze "
            "LOCATE_VISION_OLLAMA_MODEL=llava oder moondream."
            if de else
            "My vision model didn't respond — it may be too large for this "
            "machine. Try a lighter one: set LOCATE_VISION_OLLAMA_MODEL=llava "
            "(or moondream) and restart."
        )

    # 2) Fallback: on-board 80-class detector (the mockable I/O seam).
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
        return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"
    except Exception as e:
        return f"Kamera-Fehler: {e}" if de else f"Camera error: {e}"

    if not detections:
        return "Ich erkenne nichts Bestimmtes." if de else "I don't see anything recognizable."

    labels = [f"{d['label']} ({d['score']:.0%})" for d in detections[:5]]
    listed = ", ".join(labels)
    return f"Ich sehe: {listed}." if de else f"I can see: {listed}."


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
