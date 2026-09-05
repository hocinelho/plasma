"""
Face + hand perception via MediaPipe Tasks (Apache 2.0).

Two lazy-loaded MediaPipe models:
  * FaceLandmarker (with blendshapes) — smile, sleepy, wink, eyes-closed
  * HandLandmarker (21 keypoints/hand) — finger counting + gestures

Everything runs on the CPU in real time, so it's safe for always-on use, and
the same models have a JavaScript build for in-browser/phone use later.

The landmark -> meaning logic (`_finger_states`, `classify_gesture`,
`classify_expression`) is split into pure functions so it can be unit-tested
without a camera or the heavy MediaPipe runtime.

Output of Perceiver.perceive(frame_bgr):
    {
      "faces": [ {expression, smiling, wink, eyes_closed, ...} ],
      "hands": [ {handedness, finger_count, fingers, gesture, raised} ],
    }
"""
from __future__ import annotations
import logging
import urllib.request
from pathlib import Path

import numpy as np

log = logging.getLogger("plasma.vision.perception")

# ── MediaPipe model assets (auto-downloaded on first use) ────────────────────
_FACE_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_HAND_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
_FACE_NAME = "face_landmarker.task"
_HAND_NAME = "hand_landmarker.task"

# ── Hand landmark indices (MediaPipe 21-point model) ─────────────────────────
_THUMB_TIP, _THUMB_IP = 4, 3
_FINGER_TIPS = (8, 12, 16, 20)   # index, middle, ring, pinky tips
_FINGER_PIPS = (6, 10, 14, 18)   # matching PIP joints

# ── Expression thresholds (blendshape scores 0..1) ───────────────────────────
_SMILE_T = 0.35
_BLINK_CLOSED_T = 0.5
_BLINK_OPEN_T = 0.2
_JAW_YAWN_T = 0.5


def _xy(point) -> tuple[float, float]:
    """Read (x, y) from a MediaPipe landmark or any object/tuple with x,y."""
    if hasattr(point, "x"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _finger_states(landmarks, handedness: str) -> list[int]:
    """Return [thumb, index, middle, ring, pinky] as 1=extended, 0=folded.

    Landmarks are normalized (0..1), origin top-left. The four fingers are
    "extended" when the tip sits above (smaller y) its PIP joint — robust for an
    upright hand. The thumb is horizontal, so it's compared on x using the
    reported handedness (MediaPipe reports handedness for the mirrored selfie
    view; thumb direction may flip if your camera isn't mirrored).
    """
    states: list[int] = []
    tx, _ = _xy(landmarks[_THUMB_TIP])
    ix, _ = _xy(landmarks[_THUMB_IP])
    if handedness.lower().startswith("r"):
        states.append(1 if tx < ix else 0)
    else:
        states.append(1 if tx > ix else 0)
    for tip, pip in zip(_FINGER_TIPS, _FINGER_PIPS):
        _, ty = _xy(landmarks[tip])
        _, py = _xy(landmarks[pip])
        states.append(1 if ty < py else 0)
    return states


def count_fingers(landmarks, handedness: str) -> int:
    """How many fingers are extended (0–5)."""
    return sum(_finger_states(landmarks, handedness))


# How far above the wrist the middle knuckle must sit, in frame heights, for
# the hand to count as held up. Small, because the distance from wrist to
# knuckle is only ~0.1 of the frame at a normal sitting distance — but not
# zero, or a hand resting palm-down on the desk would qualify.
_RAISED_MARGIN = 0.04


def is_raised(landmarks) -> bool:
    """True if the hand is held up — the gesture you make to say hello.

    Judged by the hand's ORIENTATION, not its position in the frame. The
    first version asked whether the wrist was in the upper half of the
    picture, which sounds equivalent and is not: sitting at a laptop, the
    camera fills the upper half with your face, so waving next to your head
    puts the wrist at roughly 0.6 and the greeting never fired. You had to
    hold your hand up by the ceiling for it to count.

    Fingers up, wrist below them — that is a raised hand wherever it happens
    to be in the frame, whether you are sitting close, far, high or low.
    """
    _, wrist_y = _xy(landmarks[0])
    _, knuckle_y = _xy(landmarks[9])       # middle-finger MCP, the palm's top
    return (wrist_y - knuckle_y) > _RAISED_MARGIN


def classify_gesture(landmarks, handedness: str) -> str | None:
    """Name the hand gesture, or None if it doesn't match a known one."""
    thumb, index, middle, ring, pinky = _finger_states(landmarks, handedness)
    if not any((thumb, index, middle, ring, pinky)):
        return "fist"
    if thumb and index and middle and ring and pinky:
        return "open_palm"
    # Victory / peace — index + middle up, ring + pinky down (thumb don't-care).
    if index and middle and not ring and not pinky:
        return "victory"
    if thumb and not index and not middle and not ring and not pinky:
        return "thumbs_up"
    if index and not middle and not ring and not pinky and not thumb:
        return "pointing"
    return None


def classify_expression(blendshapes: dict) -> dict:
    """Turn MediaPipe face blendshape scores into a friendly expression dict."""
    smile = (blendshapes.get("mouthSmileLeft", 0.0) + blendshapes.get("mouthSmileRight", 0.0)) / 2
    blink_l = blendshapes.get("eyeBlinkLeft", 0.0)
    blink_r = blendshapes.get("eyeBlinkRight", 0.0)
    jaw = blendshapes.get("jawOpen", 0.0)

    wink: str | None = None
    if blink_l > _BLINK_CLOSED_T and blink_r < _BLINK_OPEN_T:
        wink = "left"
    elif blink_r > _BLINK_CLOSED_T and blink_l < _BLINK_OPEN_T:
        wink = "right"

    eyes_closed = blink_l > _BLINK_CLOSED_T and blink_r > _BLINK_CLOSED_T
    smiling = smile > _SMILE_T
    sleepy = jaw > _JAW_YAWN_T or eyes_closed

    if smiling:
        expression = "happy"
    elif sleepy:
        expression = "sleepy"
    elif wink:
        expression = "winking"
    else:
        expression = "neutral"

    return {
        "expression": expression,
        "smiling": smiling,
        "wink": wink,
        "eyes_closed": eyes_closed,
        "smile_score": round(smile, 2),
        "jaw_open": round(jaw, 2),
        "blink_left": round(blink_l, 2),
        "blink_right": round(blink_r, 2),
    }


# ── Human-readable summary ───────────────────────────────────────────────────

_GESTURE_EN = {
    "victory": "a victory sign",
    "thumbs_up": "a thumbs up",
    "open_palm": "an open hand",
    "fist": "a fist",
    "pointing": "a pointing finger",
}
_GESTURE_DE = {
    "victory": "ein Victory-Zeichen",
    "thumbs_up": "Daumen hoch",
    "open_palm": "eine offene Hand",
    "fist": "eine Faust",
    "pointing": "einen zeigenden Finger",
}
_EXPR_EN = {
    "happy": "you look happy",
    "sleepy": "you look sleepy",
    "winking": "you're winking",
    "neutral": "your expression is neutral",
}
_EXPR_DE = {
    "happy": "du siehst glücklich aus",
    "sleepy": "du siehst müde aus",
    "winking": "du zwinkerst",
    "neutral": "dein Ausdruck ist neutral",
}


def summarize(perception: dict, de: bool = False) -> str:
    """Build a natural-language summary of a perception result."""
    faces = perception.get("faces", [])
    hands = perception.get("hands", [])
    parts: list[str] = []

    if faces:
        f = faces[0]
        parts.append((_EXPR_DE if de else _EXPR_EN).get(f["expression"], ""))
        if f.get("wink") and f["expression"] != "winking":
            parts.append("und du zwinkerst" if de else "and you're winking")

    for h in hands:
        g = h.get("gesture")
        n = h.get("finger_count", 0)
        if g and g in (_GESTURE_DE if de else _GESTURE_EN):
            parts.append(
                f"ich sehe {(_GESTURE_DE if de else _GESTURE_EN)[g]}"
                if de
                else f"I see {(_GESTURE_EN)[g]}"
            )
        else:
            parts.append(
                f"ich zähle {n} Finger" if de else f"I count {n} finger{'s' if n != 1 else ''}"
            )

    if not parts:
        return "Ich sehe niemanden." if de else "I don't see anyone."
    sentence = ", ".join(p for p in parts if p)
    return sentence[0].upper() + sentence[1:] + "."


# ── MediaPipe runtime (lazy) ─────────────────────────────────────────────────

def _model_path(name: str, url: str) -> Path:
    from backend.core.config import config
    dest = config.VISION_MODEL_DIR / name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading MediaPipe model %s → %s", name, dest)
        urllib.request.urlretrieve(url, dest)
        log.info("Model downloaded: %s", dest)
    return dest


class Perceiver:
    """Lazy-loaded MediaPipe face + hand perception (thread-safe after load)."""

    def __init__(self, max_hands: int = 2):
        self._max_hands = max_hands
        self._face = None
        self._hand = None

    def _load(self) -> None:
        if self._face is not None and self._hand is not None:
            return
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
        except ImportError as e:
            raise ImportError(
                "mediapipe is not installed. Run: pip install mediapipe"
            ) from e

        face_model = _model_path(_FACE_NAME, _FACE_URL)
        hand_model = _model_path(_HAND_NAME, _HAND_URL)

        self._face = mp_vision.FaceLandmarker.create_from_options(
            mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(face_model)),
                output_face_blendshapes=True,
                num_faces=1,
            )
        )
        self._hand = mp_vision.HandLandmarker.create_from_options(
            mp_vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(hand_model)),
                num_hands=self._max_hands,
            )
        )
        log.info("MediaPipe face + hand landmarkers loaded")

    def perceive(self, frame_bgr: np.ndarray) -> dict:
        """Detect faces + hands in a BGR frame; return structured perception."""
        self._load()
        import mediapipe as mp

        rgb = frame_bgr[:, :, ::-1].copy()  # BGR → RGB, contiguous
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        face_res = self._face.detect(mp_image)
        hand_res = self._hand.detect(mp_image)

        faces = []
        for bs in (face_res.face_blendshapes or []):
            scores = {c.category_name: c.score for c in bs}
            faces.append(classify_expression(scores))

        hands = []
        hand_lms = hand_res.hand_landmarks or []
        handed = hand_res.handedness or []
        for i, lms in enumerate(hand_lms):
            label = handed[i][0].category_name if i < len(handed) and handed[i] else "Right"
            states = _finger_states(lms, label)
            hands.append({
                "handedness": label,
                "finger_count": sum(states),
                "fingers": states,
                "gesture": classify_gesture(lms, label),
                "raised": is_raised(lms),
            })

        return {"faces": faces, "hands": hands}


# Module-level singleton — shared across skill, endpoints, and WS stream.
_perceiver: Perceiver | None = None


def get_perceiver() -> Perceiver:
    global _perceiver
    if _perceiver is None:
        _perceiver = Perceiver()
    return _perceiver
