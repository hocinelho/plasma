"""Open-vocabulary visual search via locate-anything.cpp (NVIDIA LocateAnything-3B).

Unlike the MediaPipe `vision` skill (fixed 80 COCO classes), this finds ANY
object described in natural language — "find my keys", "where is my coffee mug".

Setup (one-time, on the machine running Plasma):
  1. git clone --recursive https://github.com/mudler/locate-anything.cpp
  2. cmake -B build -DLA_BUILD_CLI=ON && cmake --build build -j
  3. Download a GGUF model from huggingface.co/mudler/locate-anything.cpp-gguf
  4. Set in .env:
       LOCATE_ANYTHING_BIN=/path/to/build/locate-anything-cli
       LOCATE_ANYTHING_MODEL=/path/to/locate-anything-q8_0.gguf

CLI contract (from the repo):
  locate-anything-cli detect --model <gguf> --input <img> --prompt <text>
      --mode hybrid --output boxes.json
  → writes {"detections":[{"label":"keys","box":[x,y,w,h]}, ...]} to boxes.json
"""
from __future__ import annotations
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("plasma.skill.locate")

META = {
    "name": "locate",
    "description": "Find any object by description using the camera (open-vocabulary).",
    "triggers": [
        # English
        "find my",
        "where is my",
        "where are my",
        "can you find",
        "can you see my",
        "locate my",
        "look for my",
        "help me find",
        "have you seen my",
        # German
        "finde mein",
        "finde meine",
        "wo ist mein",
        "wo ist meine",
        "wo sind meine",
        "kannst du mein",
        "such mein",
        "suche mein",
    ],
    "example_utterances": [
        "Find my keys",
        "Where is my phone?",
        "Can you see my coffee mug?",
        "Wo ist mein Schlüssel?",
        "Finde meine Brille",
    ],
}

_OBJ_RE = re.compile(
    r"(?:find|locate|look for|where (?:is|are)|can you (?:find|see)|help me find|have you seen"
    r"|finde|wo (?:ist|sind)|such(?:e)?|kannst du)\s+"
    r"(?:my\s+|mein(?:e|en|em|er)?\s+|the\s+)?(.+?)(?:\s*[.?!]|$)",
    re.I,
)


def _is_available() -> bool:
    from backend.core.config import config
    return bool(
        config.LOCATE_ANYTHING_SERVER_URL.strip()
        or (config.LOCATE_ANYTHING_BIN.strip() and config.LOCATE_ANYTHING_MODEL.strip())
    )


def _extract_object(utterance: str) -> str | None:
    m = _OBJ_RE.search(utterance)
    if not m:
        return None
    obj = m.group(1).strip().rstrip(".,!?").lower()
    return obj or None


def _describe_location(box: list, img_w: int, img_h: int, de: bool) -> str:
    """Turn a bounding box into a rough spoken location (left/center/right, top/bottom)."""
    try:
        x, y, w, h = box[0], box[1], box[2], box[3]
        cx = x + w / 2
        cy = y + h / 2
    except Exception:
        return ""
    horiz_en = "on the left" if cx < img_w / 3 else "on the right" if cx > 2 * img_w / 3 else "in the center"
    horiz_de = "links" if cx < img_w / 3 else "rechts" if cx > 2 * img_w / 3 else "in der Mitte"
    vert_en = "near the top" if cy < img_h / 3 else "near the bottom" if cy > 2 * img_h / 3 else ""
    vert_de = "oben" if cy < img_h / 3 else "unten" if cy > 2 * img_h / 3 else ""
    if de:
        return f"{horiz_de}{(' ' + vert_de) if vert_de else ''}"
    return f"{horiz_en}{(' ' + vert_en) if vert_en else ''}"


def _run_detection_remote(image_path: str, prompt: str) -> list[dict]:
    """POST image to a remote locate-anything server and return detections."""
    from backend.core.config import config
    from backend.core.http_client import post as http_post

    url = config.LOCATE_ANYTHING_SERVER_URL.rstrip("/") + "/detect"
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    import base64
    payload = {
        "image_b64": base64.b64encode(image_bytes).decode(),
        "prompt": prompt,
        "mode": config.LOCATE_ANYTHING_MODE,
    }
    log.info("Remote locate-anything: POST %s prompt=%r", url, prompt)
    resp = http_post(url, json=payload, timeout=config.LOCATE_ANYTHING_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("detections", []) if isinstance(data, dict) else []


def _run_detection(image_path: str, prompt: str) -> list[dict]:
    """Call locate-anything-cli (or remote server) and return parsed detections."""
    from backend.core.config import config

    if config.LOCATE_ANYTHING_SERVER_URL.strip():
        return _run_detection_remote(image_path, prompt)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name

    cmd = [
        config.LOCATE_ANYTHING_BIN,
        "detect",
        "--model", config.LOCATE_ANYTHING_MODEL,
        "--input", image_path,
        "--prompt", prompt,
        "--mode", config.LOCATE_ANYTHING_MODE,
        "--output", out_path,
    ]
    log.info("Running locate-anything: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.LOCATE_ANYTHING_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"locate-anything-cli failed: {proc.stderr.strip()[:200]}")

    # Prefer the JSON output file; fall back to parsing stdout.
    raw = ""
    try:
        raw = Path(out_path).read_text(encoding="utf-8")
    except Exception:
        raw = proc.stdout
    finally:
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass

    try:
        data = json.loads(raw)
    except Exception:
        # Some builds print JSON to stdout instead
        data = json.loads(proc.stdout)
    return data.get("detections", []) if isinstance(data, dict) else []


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    if not _is_available():
        return (
            "LocateAnything ist nicht eingerichtet. Setze LOCATE_ANYTHING_BIN und "
            "LOCATE_ANYTHING_MODEL in der .env."
            if de
            else "LocateAnything isn't set up. Add LOCATE_ANYTHING_BIN and "
            "LOCATE_ANYTHING_MODEL to your .env (see the locate skill docstring)."
        )

    obj = _extract_object(utterance)
    if not obj:
        return (
            "Was soll ich suchen? Sag z.B. 'Finde meinen Schlüssel'."
            if de
            else "What should I look for? Try 'find my keys'."
        )

    # Grab a frame from the local camera and write it to a temp PNG
    try:
        from backend.core.config import config
        from backend.modules.vision.capture import snapshot
        import numpy as np  # noqa: F401

        frame = snapshot(config.CAMERA_DEVICE)
        img_h, img_w = frame.shape[0], frame.shape[1]

        import cv2
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            img_path = tf.name
        cv2.imwrite(img_path, frame)
    except ImportError as e:
        return (
            f"Kamera-Pakete fehlen ({e}). Installiere: pip install opencv-python"
            if de
            else f"Camera packages missing ({e}). Install: pip install opencv-python"
        )
    except Exception as e:
        return (
            f"Kamera nicht verfügbar: {e}"
            if de
            else f"Camera not available: {e}"
        )

    try:
        detections = _run_detection(img_path, obj)
    except subprocess.TimeoutExpired:
        return (
            "Die Suche hat zu lange gedauert."
            if de
            else "The search took too long."
        )
    except Exception as e:
        log.warning("locate detection failed: %s", e)
        return (
            f"Suche fehlgeschlagen: {e}"
            if de
            else f"Search failed: {e}"
        )
    finally:
        try:
            Path(img_path).unlink(missing_ok=True)
        except Exception:
            pass

    if not detections:
        return (
            f"Ich kann '{obj}' nicht sehen."
            if de
            else f"I can't see your {obj}."
        )

    best = detections[0]
    loc = _describe_location(best.get("box", []), img_w, img_h, de)
    if de:
        return f"Ich sehe {obj} {loc}." if loc else f"Ich sehe {obj}."
    return f"I found your {obj} {loc}." if loc else f"I found your {obj}."


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
