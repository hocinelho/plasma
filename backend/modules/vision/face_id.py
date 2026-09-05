"""
Face identity recognition via DeepFace (MIT-licensed, fully local).

Mirrors the speaker_id design so the camera side feels like the voice side:
- DeepFace is an OPTIONAL dependency (it pulls in tensorflow/onnx). If it isn't
  installed, is_available() returns False and recognition is silently skipped —
  Plasma keeps working, it just can't name who it sees.
- Enrolled faces live under .plasma/faces/<name>/*.jpg. DeepFace.find() builds
  and caches embeddings from that folder.
- Enrollment is camera-driven: "remember my face as Hocine" (EN) /
  "merke dir mein gesicht als Hocine" (DE).
- Identity is heavier than landmark tracking (~100-300 ms), so callers run it
  occasionally (every few seconds) rather than every frame.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Optional

import numpy as np

from backend.core.config import config

log = logging.getLogger("plasma.vision.face_id")

FACES_DIR = config.PLASMA_DIR / "faces"

# "remember/memorize/save/register/learn my face as <name>" (+ German)
_ENROLL_RE = re.compile(
    r"(?:remember|memorize|memorise|save|enroll|register|learn|this\s+is)\s+my\s+face\s+as\s+([a-zA-ZÀ-ÿ]+)"
    r"|merke?\s*(?:dir)?\s*mein\s+gesicht\s+als\s+([a-zA-ZÀ-ÿ]+)",
    re.IGNORECASE,
)
# Enrollment INTENT even without a name ("memorize my face", "save my face to
# your memory", "remember me").
_ENROLL_INTENT_RE = re.compile(
    r"\b(remember|memorize|memorise|save|register|learn)\s+(my\s+face|me)\b"
    r"|\bmerke?\s*(dir)?\s*mein\s+gesicht\b",
    re.IGNORECASE,
)

_lock = threading.Lock()


def parse_enroll_command(text: str) -> Optional[str]:
    """Return the person's name if the utterance names one for face enrollment."""
    m = _ENROLL_RE.search((text or "").strip())
    if not m:
        return None
    name = m.group(1) or m.group(2)
    return name.strip().capitalize() if name else None


def is_enroll_intent(text: str) -> bool:
    """True if the utterance asks to save the face, even without naming a person."""
    return bool(_ENROLL_INTENT_RE.search((text or "").strip()))


# The answer to "what's your name?" — a whole sentence, or just the name.
# Deliberately separate from _ENROLL_RE: that one has to be sure, because it
# fires unprompted out of ordinary conversation. This one only ever runs on
# the turn straight after she asked, where "Hocine" is a complete answer and
# demanding "remember my face as Hocine" would be absurd.
_OFFERED_NAME_RE = re.compile(
    r"^(?:my\s+name\s+is|i\s*(?:'m|\s+am)|it\s*(?:'s|\s+is)|this\s+is|call\s+me|"
    r"ich\s+(?:heiße|heisse|bin)|mein\s+name\s+ist|nenn\s+mich)?"
    r"\s*([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'-]{1,30})\s*[.!]?$",
    re.IGNORECASE,
)

# Words that pass the shape test above but are answers to a different
# question — mostly refusals. Enrolling a face as "No" would be permanent and
# would need finding and deleting by hand.
_NOT_A_NAME = frozenset({
    "no", "nope", "nothing", "none", "never", "nein", "nichts", "niemand",
    "yes", "yeah", "yep", "ja", "ok", "okay", "sure", "stop", "cancel",
    "later", "nevermind", "später", "abbrechen", "who", "what", "why",
    "wer", "was", "warum", "hello", "hi", "hallo", "hey", "thanks", "danke",
})


def parse_offered_name(text: str) -> Optional[str]:
    """The name in an answer to "what's your name?", or None.

    Accepts a bare "Hocine" as readily as "my name is Hocine", because that
    is how people actually answer. Returns None for anything that is not a
    plausible single name — a refusal, a question back, or a whole sentence —
    so declining to answer leaves nothing enrolled rather than saving a face
    under the word "no".
    """
    m = _OFFERED_NAME_RE.match((text or "").strip())
    if not m:
        return None
    name = m.group(1).strip()
    if name.lower() in _NOT_A_NAME:
        return None
    return name.capitalize()


def is_available() -> bool:
    """True if DeepFace can be imported (optional heavy dependency)."""
    if not config.FACE_ID_ENABLED:
        return False
    try:
        import deepface  # noqa: F401
        return True
    except Exception:
        return False


def list_people() -> list[str]:
    """Names with at least one enrolled face image."""
    if not FACES_DIR.exists():
        return []
    return sorted(
        p.name for p in FACES_DIR.iterdir()
        if p.is_dir() and any(p.glob("*.jpg"))
    )


def _invalidate_cache() -> None:
    """Remove DeepFace's cached representation pickles so new faces are seen."""
    try:
        for pkl in FACES_DIR.glob("*.pkl"):
            pkl.unlink(missing_ok=True)
        for pkl in FACES_DIR.glob("ds_*.pkl"):
            pkl.unlink(missing_ok=True)
    except Exception:
        pass


def enroll(name: str, frame_bgr: np.ndarray) -> str:
    """Save a face crop for `name`. Returns a user-facing confirmation string."""
    if not is_available():
        return (
            "Face recognition isn't installed. Run: pip install deepface — "
            "then look at the camera and say 'remember my face as <your name>'."
        )
    try:
        import cv2
    except ImportError:
        return "Camera packages missing. Install: pip install opencv-python"

    with _lock:
        person_dir = FACES_DIR / name
        person_dir.mkdir(parents=True, exist_ok=True)
        existing = len(list(person_dir.glob("*.jpg")))
        out = person_dir / f"{existing + 1:03d}.jpg"
        cv2.imwrite(str(out), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        _invalidate_cache()
        log.info("face_id: enrolled %s (%d image%s total)", name, existing + 1, "" if existing == 0 else "s")

    return f"Got it — I'll remember your face, {name}."


def identify(frame_bgr: np.ndarray) -> tuple[Optional[str], float]:
    """Return (name, distance) of the best match, or (None, 0.0) if unknown.

    Lower distance = better match. Returns (None, …) when nobody is enrolled,
    DeepFace is missing, or no enrolled face is close enough.
    """
    if not is_available() or not list_people():
        return None, 0.0
    try:
        from deepface import DeepFace

        results = DeepFace.find(
            img_path=frame_bgr,
            db_path=str(FACES_DIR),
            model_name=config.FACE_ID_MODEL,
            enforce_detection=False,
            silent=True,
        )
    except Exception as e:
        log.warning("face_id: identify failed: %s", e)
        return None, 0.0

    # DeepFace.find returns a list of DataFrames (one per detected face).
    for df in results:
        if df is None or len(df) == 0:
            continue
        row = df.iloc[0]
        identity_path = str(row.get("identity", ""))
        # distance column name varies by version (e.g. "distance" or
        # "<model>_<metric>"); take whichever numeric distance is present.
        dist = None
        for col in df.columns:
            if "distance" in col.lower():
                dist = float(row[col])
                break
        # The enrolled person's name is the parent folder of the matched image.
        try:
            from pathlib import Path
            name = Path(identity_path).parent.name
        except Exception:
            name = None
        if name:
            return name, dist if dist is not None else 0.0

    return None, 0.0
