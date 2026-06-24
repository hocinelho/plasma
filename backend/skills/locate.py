"""Open-vocabulary visual search — finds ANY object by natural language description.

Three backends, tried in priority order:

1. Cloud Vision LLM (Gemini / OpenAI-vision-compatible) — instant, zero install,
   uses the CLOUD_API_KEY already in .env. Works from phones/laptops with no
   extra setup. Requires internet.

2. Ollama moondream — offline fallback, ~1.9 GB, fast on CPU.
   Enable: `ollama pull moondream`  then set LOCATE_VISION_OLLAMA_MODEL=moondream

3. locate-anything CLI — heavy offline option (6 GB GGUF, C++ build).
   Kept for users who have it set up and want GPU-accelerated local inference.
   Enabled when LOCATE_ANYTHING_BIN + LOCATE_ANYTHING_MODEL are set.

Phones/laptops never need to install anything — they connect to Plasma's browser
UI and the vision runs server-side.
"""
from __future__ import annotations
import base64
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from backend.core.http_client import post as http_post

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

_VISION_PROMPT_EN = (
    "Look at this image. Do you see a {obj} anywhere? "
    "Reply with one sentence: either where you see it "
    "(e.g. 'Yes, the {obj} is on the left.') or 'No, I do not see a {obj}.'"
)
_VISION_PROMPT_DE = (
    "Schau dir dieses Bild an. Siehst du {obj}? "
    "Antworte in einem Satz: entweder wo du es siehst "
    "(z.B. 'Ja, {obj} ist links.') oder 'Nein, ich sehe {obj} nicht.'"
)


def _extract_object(utterance: str) -> str | None:
    m = _OBJ_RE.search(utterance)
    if not m:
        return None
    obj = m.group(1).strip().rstrip(".,!?").lower()
    return obj or None


def _describe_location(box: list, img_w: int, img_h: int, de: bool) -> str:
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


# ── Backend 1: Cloud Vision LLM ──────────────────────────────────────────────

def _cloud_vision_available() -> bool:
    from backend.core.config import config
    return bool(config.CLOUD_API_KEY.strip())


def _cloud_chat_completions_url() -> str:
    """Build the correct chat/completions URL for the configured provider."""
    from backend.core.config import config
    base = config.CLOUD_BASE_URL.rstrip("/")
    # Gemini OpenAI-compat: ends in /openai/ or /openai
    if "generativelanguage.googleapis.com" in base:
        return f"{base}/chat/completions"
    # OpenRouter: always /api/v1/chat/completions regardless of CLOUD_BASE_URL path
    if "openrouter.ai" in base:
        return "https://openrouter.ai/api/v1/chat/completions"
    # Groq, Cerebras, generic OpenAI-compat: append /chat/completions
    return f"{base}/chat/completions"


def _locate_via_cloud(image_path: str, obj: str, de: bool) -> str:
    """Send image + prompt to the configured cloud LLM (Gemini / OpenAI vision)."""
    from backend.core.config import config

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    prompt = (_VISION_PROMPT_DE if de else _VISION_PROMPT_EN).format(obj=obj)
    url = _cloud_chat_completions_url()
    headers = {
        "Authorization": f"Bearer {config.CLOUD_API_KEY}",
        "Content-Type": "application/json",
    }

    locate_model = getattr(config, "LOCATE_CLOUD_MODEL", "").strip()
    # Prefer LOCATE_CLOUD_MODEL; fall back to CLOUD_MODEL if not set or if it
    # returns 404 (model removed/renamed on the provider).
    models_to_try = [m for m in [locate_model, config.CLOUD_MODEL] if m]
    # Deduplicate while preserving order
    seen: set[str] = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]

    last_err: Exception | None = None
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 120,
            "temperature": 0.1,
        }
        log.info("locate: cloud vision POST %s model=%s", url, model)
        resp = http_post(url, json=payload, headers=headers, timeout=20.0)
        if resp.status_code == 404:
            log.warning("locate: cloud model %s not found (404), trying next model", model)
            last_err = Exception(f"model not found: {model}")
            continue
        if resp.status_code >= 400:
            # Log the provider's actual error message so misconfig is visible.
            body = resp.text[:300]
            log.warning("locate: cloud model %s -> %s: %s", model, resp.status_code, body)
            # 400 often means the model can't accept images (text-only model).
            # Fall through to the next candidate model rather than aborting.
            last_err = Exception(f"{resp.status_code}: {body}")
            continue
        return _parse_vision_response(
            resp.json()["choices"][0]["message"]["content"].strip(), obj, de
        )

    raise last_err or RuntimeError("no cloud vision model available")


# ── Backend 2: Ollama moondream ───────────────────────────────────────────────

def _ollama_vision_available() -> bool:
    from backend.core.config import config
    return bool(getattr(config, "LOCATE_VISION_OLLAMA_MODEL", "").strip())


_NOT_FOUND_WORDS = frozenset([
    "no,", "no.", "nein", "not see", "cannot see", "can't see", "do not see",
    "don't see", "not visible", "not in", "not find", "cannot find",
    "can't find", "don't find", "keine", "nicht sehen", "not present",
    "no sign", "unable to see", "i don't", "i can't",
])


def _parse_vision_response(text: str, obj: str, de: bool) -> str:
    """Normalise a raw vision-model reply into a clean locate response.

    Small models (moondream) answer in many different styles. This helper:
    - Detects "not found" semantics and returns a clean "I cannot see X" message
      rather than letting a confusing model reply reach the user.
    - Strips leading "Yes, " / "Ja, " when the object was found.
    - Wraps bare location phrases ("on the left") in a natural sentence.
    """
    lower = text.lower()

    # If the model says it doesn't see the object, normalise to a clean message.
    if any(w in lower for w in _NOT_FOUND_WORDS):
        return (
            f"Ich kann {obj} nicht sehen."
            if de
            else f"I cannot see your {obj}."
        )

    # Strip leading "Yes, " / "Ja, " confirmations.
    for prefix in ("yes, the ", "yes, i can see ", "yes, ", "ja, "):
        if lower.startswith(prefix):
            text = text[len(prefix):]
            lower = text.lower()
            break

    # Wrap bare phrases like "on the table" → "Your keys are on the table."
    has_subject = any(lower.startswith(w) for w in (
        "your", "the ", "i ", "it ", "ich", "dein", "es ",
    ))
    if not has_subject:
        return f"Dein {obj} ist {text}." if de else f"Your {obj} is {text}."

    return text


# ── Backend 2: Ollama moondream ───────────────────────────────────────────────

def _locate_via_ollama(image_path: str, obj: str, de: bool) -> str:
    """Send image to Ollama moondream (or any vision model) for object location."""
    from backend.core.config import config

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    prompt = (_VISION_PROMPT_DE if de else _VISION_PROMPT_EN).format(obj=obj)
    model = config.LOCATE_VISION_OLLAMA_MODEL
    base = config.OLLAMA_BASE_URL.rstrip("/")

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        # temperature 0 can cause degenerate empty output in small models;
        # 0.1 is near-deterministic while avoiding blank responses.
        "options": {"temperature": 0.1},
    }

    # moondream occasionally returns an empty string on the first pass; retry
    # once before giving up so a transient blank doesn't surface as an error.
    text = ""
    for attempt in range(2):
        resp = http_post(f"{base}/api/generate", json=payload, timeout=60.0)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip().strip("'\"")
        if text:
            break
        log.warning("locate: moondream returned empty response (attempt %d)", attempt + 1)

    if not text:
        # Don't surface a raw error to the user — say honestly we couldn't see.
        return (
            f"Ich konnte {obj} nicht klar erkennen. Versuch es nochmal."
            if de
            else f"I couldn't get a clear look at your {obj}. Please try again."
        )
    return _parse_vision_response(text, obj, de)


# ── Backend 3: locate-anything CLI ───────────────────────────────────────────

def _cli_available() -> bool:
    from backend.core.config import config
    return bool(
        getattr(config, "LOCATE_ANYTHING_SERVER_URL", "").strip()
        or (config.LOCATE_ANYTHING_BIN.strip() and config.LOCATE_ANYTHING_MODEL.strip())
    )


def _resolve_path(p: str) -> str:
    from backend.core.config import PROJECT_ROOT
    path = Path(p)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def _locate_via_cli(image_path: str, obj: str, img_w: int, img_h: int, de: bool) -> str:
    from backend.core.config import config

    if getattr(config, "LOCATE_ANYTHING_SERVER_URL", "").strip():
        url = config.LOCATE_ANYTHING_SERVER_URL.rstrip("/") + "/detect"
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = http_post(url, json={"image_b64": b64, "prompt": obj, "mode": config.LOCATE_ANYTHING_MODE},
                         timeout=config.LOCATE_ANYTHING_TIMEOUT)
        resp.raise_for_status()
        detections = resp.json().get("detections", [])
    else:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            out_path = tf.name
        cmd = [
            _resolve_path(config.LOCATE_ANYTHING_BIN), "detect",
            "--model", _resolve_path(config.LOCATE_ANYTHING_MODEL),
            "--input", image_path,
            "--prompt", obj,
            "--mode", config.LOCATE_ANYTHING_MODE,
            "--output", out_path,
        ]
        if getattr(config, "LOCATE_ANYTHING_THREADS", 0) > 0:
            cmd += ["--threads", str(config.LOCATE_ANYTHING_THREADS)]
        log.info("Running locate-anything: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=config.LOCATE_ANYTHING_TIMEOUT)
        if proc.returncode != 0:
            raise RuntimeError(f"locate-anything-cli failed: {proc.stderr.strip()[:200]}")
        try:
            raw = Path(out_path).read_text(encoding="utf-8")
        except Exception:
            raw = proc.stdout
        finally:
            Path(out_path).unlink(missing_ok=True)
        try:
            data = json.loads(raw)
        except Exception:
            data = json.loads(proc.stdout)
        detections = data.get("detections", []) if isinstance(data, dict) else []

    if not detections:
        return f"Ich kann '{obj}' nicht sehen." if de else f"I can't see your {obj}."
    best = detections[0]
    loc = _describe_location(best.get("box", []), img_w, img_h, de)
    if de:
        return f"Ich sehe {obj} {loc}." if loc else f"Ich sehe {obj}."
    return f"I found your {obj} {loc}." if loc else f"I found your {obj}."


def _is_available() -> bool:
    return _cloud_vision_available() or _ollama_vision_available() or _cli_available()


# ── Main skill entry point ────────────────────────────────────────────────────

def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    if not _is_available():
        return (
            "LocateAnything ist nicht eingerichtet. Setze CLOUD_API_KEY (Gemini) oder "
            "LOCATE_VISION_OLLAMA_MODEL=moondream in der .env."
            if de
            else "Locate isn't set up. Add CLOUD_API_KEY (Gemini, already free) or "
            "set LOCATE_VISION_OLLAMA_MODEL=moondream in your .env."
        )

    obj = _extract_object(utterance)
    if not obj:
        return (
            "Was soll ich suchen? Sag z.B. 'Finde meinen Schlüssel'."
            if de
            else "What should I look for? Try 'find my keys'."
        )

    try:
        from backend.core.config import config
        from backend.modules.vision.capture import snapshot
        import cv2

        frame = snapshot(config.CAMERA_DEVICE)
        img_h, img_w = frame.shape[0], frame.shape[1]
        # Downscale to max 1024px on the long edge before sending to a cloud
        # vision model: smaller payloads upload faster and avoid 400 errors from
        # models that cap input image size. img_w/img_h above stay as the
        # ORIGINAL dims so _describe_location math is unaffected (it only matters
        # for the CLI tier, which reads the resized file but returns relative box).
        max_edge = 1024
        long_edge = max(img_h, img_w)
        if long_edge > max_edge:
            scale = max_edge / long_edge
            new_size = (int(img_w * scale), int(img_h * scale))
            frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            img_path = tf.name
        cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_bytes = Path(img_path).stat().st_size
        log.info(
            "locate: captured %dx%d image → %s (%.1f KB)",
            frame.shape[1], frame.shape[0], img_path, img_bytes / 1024,
        )
        if img_bytes < 1024:
            return (
                "Das Kamerabild ist schwarz oder leer. Prüfe ob die Kamera frei ist."
                if de
                else "Camera image is black or empty — make sure no other app is using the webcam."
            )
    except ImportError as e:
        return (
            f"Kamera-Pakete fehlen ({e}). Installiere: pip install opencv-python"
            if de
            else f"Camera packages missing ({e}). Install: pip install opencv-python"
        )
    except Exception as e:
        return f"Kamera nicht verfügbar: {e}" if de else f"Camera not available: {e}"

    last_err = None
    try:
        # Tier 1: Cloud vision — instant, uses existing CLOUD_API_KEY
        if _cloud_vision_available():
            try:
                log.info("locate: using cloud vision (tier 1)")
                return _locate_via_cloud(img_path, obj, de)
            except Exception as e:
                log.warning("locate tier 1 (cloud) failed: %s — trying next tier", e)
                last_err = e

        # Tier 2: Ollama moondream — fast offline
        if _ollama_vision_available():
            try:
                log.info("locate: using Ollama vision (tier 2)")
                return _locate_via_ollama(img_path, obj, de)
            except Exception as e:
                log.warning("locate tier 2 (ollama) failed: %s — trying next tier", e)
                last_err = e

        # Tier 3: locate-anything CLI — heavy offline
        if _cli_available():
            try:
                log.info("locate: using CLI (tier 3)")
                return _locate_via_cli(img_path, obj, img_w, img_h, de)
            except subprocess.TimeoutExpired:
                return "Die Suche hat zu lange gedauert." if de else "The search took too long."
            except Exception as e:
                log.warning("locate tier 3 (CLI) failed: %s", e)
                last_err = e

        err_str = str(last_err) if last_err else "no backend available"
        return f"Suche fehlgeschlagen: {err_str}" if de else f"Search failed: {err_str}"
    finally:
        try:
            Path(img_path).unlink(missing_ok=True)
        except Exception:
            pass


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
