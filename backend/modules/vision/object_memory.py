"""
Personal object memory — teach Plasma YOUR specific things.

"Remember this as my keys" enrolls whatever you're holding; later "find my keys"
pins that *exact* item (not just the generic class) with a box on the frame.

How it works (no training, no AGPL, fully offline):
- MediaPipe **ImageEmbedder** (Apache 2.0, MobileNet, auto-downloads ~6 MB) turns
  an image crop into a vector. This mirrors how speaker_id/face_id use embeddings
  for voices/faces — here it's for objects.
- Enrolled crops live under .plasma/objects/<name>/*.jpg. Their embeddings are
  computed once and cached in memory.
- To find "my keys": run the object detector for candidate boxes, embed each
  crop, and pick the box whose embedding is closest (cosine) to the enrolled
  "keys" — above OBJECT_MATCH_THRESHOLD.

Optional dependency: if mediapipe isn't installed, is_available() is False and
the feature is silently skipped (locate falls back to the open-vocab VLM).

Pure helpers (cosine, crop, command parsing) are unit-testable without a camera.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from backend.core.config import config

log = logging.getLogger("plasma.vision.object_memory")

OBJECTS_DIR = config.PLASMA_DIR / "objects"

# "remember/save/learn/memorize this [object] as [my/the] <name>"  +  "this is my <name>"
# German: "merke dir das als <name>", "das ist mein/meine <name>"
_ENROLL_RE = re.compile(
    r"(?:remember|save|learn|memorize|memorise)\s+this\s+(?:object\s+)?as\s+(?:my\s+|the\s+)?(.+)"
    r"|this\s+is\s+my\s+(.+)"
    r"|merke?\s*(?:dir)?\s*(?:das|dies)\s+als\s+(?:mein(?:e|en)?\s+)?(.+)"
    r"|das\s+ist\s+mein(?:e|en)?\s+(.+)",
    re.IGNORECASE,
)

_lock = threading.Lock()
_embedder = None
# name → list[(mtime, embedding)] cache so we don't re-embed every find.
_emb_cache: dict[str, list[tuple[float, np.ndarray]]] = {}


# ── command parsing (pure) ────────────────────────────────────────────────────

def _clean_name(raw: str) -> Optional[str]:
    name = re.sub(r"[.?!,]+$", "", (raw or "").strip()).lower()
    # Never let a face-enrollment phrase be treated as an object.
    if not name or name == "face" or name.startswith("face "):
        return None
    # A sane length cap; keep it a short label.
    return name if 0 < len(name) <= 40 else None


def parse_enroll_command(text: str) -> Optional[str]:
    """Return the object name if the utterance enrolls an object, else None."""
    m = _ENROLL_RE.search((text or "").strip())
    if not m:
        return None
    raw = next((g for g in m.groups() if g), None)
    return _clean_name(raw) if raw else None


# ── geometry / math (pure) ────────────────────────────────────────────────────

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def crop(frame_bgr: np.ndarray, box: Optional[list[float]]) -> np.ndarray:
    """Crop [x, y, w, h] from a frame, clamped to bounds. None → center square."""
    h, w = frame_bgr.shape[:2]
    if box is None:
        side = min(h, w)
        x0 = (w - side) // 2
        y0 = (h - side) // 2
        return frame_bgr[y0:y0 + side, x0:x0 + side]
    x, y, bw, bh = (int(round(v)) for v in box)
    x0 = max(0, min(x, w - 1))
    y0 = max(0, min(y, h - 1))
    x1 = max(x0 + 1, min(x + bw, w))
    y1 = max(y0 + 1, min(y + bh, h))
    return frame_bgr[y0:y1, x0:x1]


# ── availability / listing ────────────────────────────────────────────────────

def is_available() -> bool:
    if not getattr(config, "OBJECT_MEMORY_ENABLED", True):
        return False
    try:
        import mediapipe  # noqa: F401
        return True
    except Exception:
        return False


def list_objects() -> list[str]:
    if not OBJECTS_DIR.exists():
        return []
    return sorted(
        p.name for p in OBJECTS_DIR.iterdir()
        if p.is_dir() and any(p.glob("*.jpg"))
    )


def is_enrolled(name: str) -> bool:
    return (name or "").strip().lower() in set(list_objects())


# ── embedding ─────────────────────────────────────────────────────────────────

_EMBEDDER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/image_embedder/"
    "mobilenet_v3_small/float32/1/mobilenet_v3_small.tflite"
)
_EMBEDDER_MODEL_NAME = "mobilenet_v3_small_embedder.tflite"


def _model_path() -> Path:
    import urllib.request
    dest = config.VISION_MODEL_DIR / _EMBEDDER_MODEL_NAME
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading MediaPipe ImageEmbedder model (~6 MB) → %s", dest)
        urllib.request.urlretrieve(_EMBEDDER_MODEL_URL, dest)
    return dest


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    import mediapipe as mp  # noqa: F401
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    options = mp_vision.ImageEmbedderOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(_model_path())),
        l2_normalize=True,
    )
    _embedder = mp_vision.ImageEmbedder.create_from_options(options)
    log.info("MediaPipe ImageEmbedder loaded")
    return _embedder


def embed(frame_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Embed a BGR image crop into a vector, or None if embedding fails."""
    try:
        import mediapipe as mp
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = _get_embedder().embed(mp_image)
        return np.asarray(result.embeddings[0].embedding, dtype=np.float32)
    except Exception as e:
        log.warning("object_memory: embed failed: %s", e)
        return None


def _enrolled_embeddings(name: str) -> list[np.ndarray]:
    """Embeddings for every enrolled crop of `name` (cached by file mtime)."""
    person_dir = OBJECTS_DIR / name
    if not person_dir.exists():
        return []
    import cv2
    out: list[np.ndarray] = []
    cached = _emb_cache.get(name, [])
    cached_by_key = {round(mt, 3): e for mt, e in cached}
    fresh: list[tuple[float, np.ndarray]] = []
    for jpg in sorted(person_dir.glob("*.jpg")):
        mt = jpg.stat().st_mtime
        emb = cached_by_key.get(round(mt, 3))
        if emb is None:
            img = cv2.imread(str(jpg))
            if img is None:
                continue
            emb = embed(img)
            if emb is None:
                continue
        fresh.append((mt, emb))
        out.append(emb)
    _emb_cache[name] = fresh
    return out


# ── enroll / find ─────────────────────────────────────────────────────────────

def enroll(name: str, frame_bgr: np.ndarray, box: Optional[list[float]] = None) -> str:
    """Save a crop of `name` from the frame. Returns a confirmation string."""
    if not is_available():
        return (
            "Object memory needs MediaPipe. Run: pip install mediapipe opencv-python — "
            "then hold the item up and say 'remember this as my keys'."
        )
    try:
        import cv2
    except ImportError:
        return "Camera packages missing. Install: pip install opencv-python"

    region = crop(frame_bgr, box)
    with _lock:
        obj_dir = OBJECTS_DIR / name
        obj_dir.mkdir(parents=True, exist_ok=True)
        n = len(list(obj_dir.glob("*.jpg")))
        cv2.imwrite(str(obj_dir / f"{n + 1:03d}.jpg"), region, [cv2.IMWRITE_JPEG_QUALITY, 90])
        _emb_cache.pop(name, None)   # force re-embed next find
        log.info("object_memory: enrolled '%s' (%d sample%s)", name, n + 1, "" if n == 0 else "s")

    return f"Got it — I'll remember your {name}. Show it a couple more times for better accuracy."


def find_in_frame(
    name: str,
    frame_bgr: np.ndarray,
    detections: list[dict],
) -> Optional[dict]:
    """Return the detection best matching enrolled `name`, or None.

    Result: {"box", "score", "label"} where score is the cosine similarity.
    """
    refs = _enrolled_embeddings(name)
    if not refs or not detections:
        return None

    threshold = float(getattr(config, "OBJECT_MATCH_THRESHOLD", 0.55))
    best, best_score = None, -1.0
    for d in detections:
        region = crop(frame_bgr, d.get("box"))
        if region.size == 0:
            continue
        emb = embed(region)
        if emb is None:
            continue
        score = max(cosine(emb, r) for r in refs)
        if score > best_score:
            best, best_score = d, score

    if best is None or best_score < threshold:
        return None
    return {"box": best["box"], "score": round(best_score, 3), "label": best.get("label", name)}
