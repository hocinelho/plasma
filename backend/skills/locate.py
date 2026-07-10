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

import time

from backend.core.http_client import post as http_post

log = logging.getLogger("plasma.skill.locate")

# ── Annotated-frame side channel ──────────────────────────────────────────────
# When locate can pin the object to a box (via the on-board EfficientDet
# detector, Apache 2.0), it draws that box on the captured frame and stashes the
# path here. /voice/chat and /chat pop it and ship the image to the UI, so the
# user *sees* exactly where their thing is — while the spoken reply stays clean
# text (no URL read aloud).
_last_annotated: dict = {"path": None, "ts": 0.0}


def _set_last_annotated(path: str) -> None:
    _last_annotated["path"] = path
    _last_annotated["ts"] = time.monotonic()


def pop_last_annotated(max_age_s: float = 30.0) -> str | None:
    """Return (once) the most recent annotated frame path if it's fresh."""
    path = _last_annotated["path"]
    if path and (time.monotonic() - _last_annotated["ts"]) <= max_age_s:
        _last_annotated["path"] = None
        return path
    return None


def _draw_and_save(frame, box, label: str) -> str | None:
    """Draw a labelled box on the frame and save it as locate_last.jpg."""
    try:
        import cv2
        x, y, w, h = (int(v) for v in box)
        color = (138, 230, 74)  # BGR — Plasma green
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
        cv2.putText(frame, label, (x, max(20, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
        from backend.core.config import config
        out = Path(config.PLASMA_DIR) / "locate_last.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), frame)
        log.info("locate: annotated '%s' at [%d,%d,%d,%d] → %s", label, x, y, w, h, out)
        return str(out)
    except Exception as e:
        log.debug("locate annotate: draw/save failed: %s", e)
        return None


def _annotate_object(frame, obj: str) -> str | None:
    """Detect ``obj`` in ``frame`` and, if found, draw its box and save a JPEG.

    Uses the already-shipped MediaPipe EfficientDet detector (offline, 80 common
    classes). Returns the saved path, or None if the object class isn't found
    (the text answer from the vision tiers still stands).
    """
    try:
        from backend.modules.vision.detector import get_detector
        dets = get_detector().detect(frame)
    except Exception as e:  # detector/opencv missing → just skip the box
        log.debug("locate annotate: detector unavailable: %s", e)
        return None

    obj_l = obj.lower()
    obj_words = [w for w in re.split(r"\s+", obj_l) if len(w) > 2]

    def _matches(label: str) -> bool:
        label = label.lower()
        if obj_l in label or label in obj_l:
            return True
        return any(w in label or label in w for w in obj_words)

    match = next((d for d in dets if _matches(d.get("label", ""))), None)
    if not match:
        return None
    cap = f"{match['label']} {int(match.get('score', 0) * 100)}%"
    return _draw_and_save(frame, match["box"], cap)


def _try_enrolled_object(frame, obj: str, img_w: int, img_h: int, de: bool) -> str | None:
    """If ``obj`` is a personally-enrolled item, pin the exact one with a box.

    Returns a finished user-facing reply (and stashes the annotated frame), or
    None to let the normal vision tiers handle it.
    """
    try:
        from backend.modules.vision import object_memory
        from backend.modules.vision.detector import get_detector
    except Exception:
        return None
    if not (object_memory.is_available() and object_memory.is_enrolled(obj)):
        return None
    try:
        dets = get_detector().detect(frame)
        match = object_memory.find_in_frame(obj, frame, dets)
    except Exception as e:
        log.debug("locate: enrolled match failed: %s", e)
        return None
    if not match:
        return None  # your item isn't in view → fall back to the VLM

    annotated = _draw_and_save(frame.copy(), match["box"], f"your {obj}")
    if annotated:
        _set_last_annotated(annotated)
    loc = _describe_location(match["box"], img_w, img_h, de)
    if de:
        return f"Ich sehe {obj} {loc}." if loc else f"Ich sehe {obj}."
    return f"I found your {obj} {loc}." if loc else f"I found your {obj}."

META = {
    "name": "locate",
    "description": "Find any object by description using the camera (open-vocabulary).",
    "triggers": [
        # English — "my"
        "find my",
        "where is my",
        "where's my",
        "where are my",
        "can you see my",
        "locate my",
        "look for my",
        "have you seen my",
        # English — "the" / "a" / bare (e.g. "find the baby", "find a phone")
        "find the",
        "find a ",
        "find an ",
        "where is the",
        "where's the",
        "where are the",
        "can you find",
        "help me find",
        "look for the",
        "look for a ",
        "locate the",
        "have you seen the",
        # German
        "finde mein",
        "finde meine",
        "finde das",
        "finde die",
        "finde den",
        "wo ist mein",
        "wo ist meine",
        "wo ist das",
        "wo ist die",
        "wo ist der",
        "wo sind meine",
        "wo sind die",
        "kannst du mein",
        "such mein",
        "suche mein",
        "such das",
        "such die",
        "such den",
    ],
    "example_utterances": [
        "Find my keys",
        "Find the baby",
        "Where is my phone?",
        "Can you see my coffee mug?",
        "Wo ist mein Schlüssel?",
        "Finde die Brille",
    ],
}

_OBJ_RE = re.compile(
    r"(?:find|locate|look for|where (?:is|are)|can you (?:find|see)|help me find|have you seen"
    r"|finde|wo (?:ist|sind)|such(?:e)?|kannst du)\s+"
    r"(?:my\s+|mein(?:e|en|em|er)?\s+|the\s+|an?\s+"
    r"|das\s+|die\s+|der\s+|den\s+|eine[nm]?\s+)?(.+?)(?:\s*[.?!]|$)",
    re.I,
)

# Cloud/capable models get a richer prompt with format guidance.
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

# moondream / small vision models need ultra-short, direct Q&A prompts.
# Complex prompts with format examples cause them to return empty strings.
_VISION_PROMPT_OLLAMA_EN = "Where is the {obj}?"
_VISION_PROMPT_OLLAMA_DE = "Wo ist {obj}?"


# Words that are never a real object on their own — usually a cut-off utterance
# ("find my …") where the actual noun never got spoken.
_NON_OBJECTS = {
    "my", "the", "a", "an", "it", "them", "that", "this",
    "mein", "meine", "meinen", "das", "die", "der", "den", "es",
}


def _extract_object(utterance: str) -> str | None:
    m = _OBJ_RE.search(utterance)
    if not m:
        return None
    obj = m.group(1).strip().rstrip(".,!?").lower()
    if not obj or obj in _NON_OBJECTS:
        return None
    return obj


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
    # moondream-specific phrasing
    "not visible in", "not in the image", "there is no", "there are no",
    "i do not see", "there's no", "doesn't appear", "does not appear",
    "not appear", "no visible", "i cannot locate", "not located",
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

# moondream describes images very reliably, but intermittently returns an empty
# string on question-form prompts. So we try the direct question first, then
# fall back to "describe the scene" + Python-side search for the object.
_DESCRIBE_PROMPT_EN = "Describe everything you see in this image in detail."
_DESCRIBE_PROMPT_DE = "Beschreibe alles, was du in diesem Bild siehst, im Detail."


def _ollama_generate(base: str, model: str, prompt: str, b64: str) -> str:
    """One Ollama /api/generate call with an image; return text (may be empty)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        # temperature 0 causes degenerate empty output in small models;
        # 0.1 is near-deterministic while avoiding blank responses.
        "options": {"temperature": 0.1},
    }
    resp = http_post(f"{base}/api/generate", json=payload, timeout=120.0)
    if resp.status_code >= 400:
        # Surface Ollama's real reason (e.g. "requires more system memory…").
        log.warning("ollama generate %s -> %s: %s", model, resp.status_code, resp.text[:300])
    resp.raise_for_status()
    return resp.json().get("response", "").strip().strip("'\"")


def _interpret_description(description: str, obj: str, de: bool) -> str:
    """Search a free-form scene description for the requested object."""
    lower = description.lower()
    # Match the whole phrase, or any meaningful word in it ("coffee mug" → "mug").
    obj_words = [w for w in re.split(r"\s+", obj.lower()) if len(w) > 2]
    found = obj.lower() in lower or any(w in lower for w in obj_words)
    if not found:
        return f"Ich kann {obj} nicht sehen." if de else f"I cannot see your {obj}."

    # Return the sentence that mentions the object so the user gets context.
    for sentence in re.split(r"(?<=[.!?])\s+", description.strip()):
        sl = sentence.lower()
        if obj.lower() in sl or any(w in sl for w in obj_words):
            s = sentence.strip()
            return f"Ich sehe {obj}: {s}" if de else f"I can see your {obj}: {s}"

    return f"Ich sehe {obj} im Bild." if de else f"I can see your {obj} in the image."


def _ollama_vision_models() -> list[str]:
    """The vision model to try first, then configured fallbacks (deduped)."""
    from backend.core.config import config
    primary = getattr(config, "LOCATE_VISION_OLLAMA_MODEL", "").strip()
    fallbacks = [
        m.strip() for m in getattr(config, "LOCATE_VISION_OLLAMA_FALLBACKS", "").split(",")
        if m.strip()
    ]
    models: list[str] = []
    for m in [primary] + fallbacks:
        if m and m not in models:
            models.append(m)
    return models


def _locate_one_model(base: str, model: str, obj: str, b64: str, de: bool) -> str | None:
    """Run the question→describe strategy for a single model. None if it blanks."""
    q_prompt = (_VISION_PROMPT_OLLAMA_DE if de else _VISION_PROMPT_OLLAMA_EN).format(obj=obj)
    for attempt in range(3):
        text = _ollama_generate(base, model, q_prompt, b64)
        if text:
            return _parse_vision_response(text, obj, de)
        log.warning("locate: %s empty on direct question (attempt %d/3)", model, attempt + 1)

    log.info("locate: question returned empty, falling back to scene description")
    desc_prompt = _DESCRIBE_PROMPT_DE if de else _DESCRIBE_PROMPT_EN
    for attempt in range(2):
        description = _ollama_generate(base, model, desc_prompt, b64)
        if description:
            log.info("locate: %s description: %s", model, description[:200])
            return _interpret_description(description, obj, de)
        log.warning("locate: %s empty on describe (attempt %d/2)", model, attempt + 1)
    return None


def _locate_via_ollama(image_path: str, obj: str, de: bool) -> str:
    """Locate via Ollama, trying the primary vision model then lighter fallbacks
    (so a model that errors — e.g. too big → 500 — doesn't kill the request)."""
    from backend.core.config import config

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    base = config.OLLAMA_BASE_URL.rstrip("/")

    for i, model in enumerate(_ollama_vision_models()):
        try:
            result = _locate_one_model(base, model, obj, b64, de)
        except Exception as e:
            log.warning("locate: model %s failed (%s) — trying fallback", model, e)
            continue
        if result is not None:
            if i > 0:
                log.info("locate: used fallback vision model %s", model)
            return result

    return (
        f"Ich konnte {obj} nicht klar erkennen. Versuch es nochmal."
        if de
        else f"I couldn't get a clear look at your {obj}. Please try again."
    )


# ── Open-vocabulary recognition ("what is this / what do you see") ────────────
# Same VLM as locate, but a free-form describe prompt so Plasma can name ANY
# object — not just the 80 classes the on-board detector knows.

_RECOGNIZE_PROMPT_EN = (
    "Look at this image and say what you see. Name the main objects and any "
    "people or animals, with their real colours, in one or two sentences. "
    "Describe ONLY what is clearly visible — do not guess or invent colours, "
    "details, or the hidden contents of any container."
)
_RECOGNIZE_PROMPT_DE = (
    "Sieh dir dieses Bild an und sag, was du siehst. Nenne die wichtigsten "
    "Objekte und Personen oder Tiere mit ihren echten Farben, in ein bis zwei "
    "Sätzen. Beschreibe NUR, was klar sichtbar ist — rate oder erfinde keine "
    "Farben, Details oder verborgenen Inhalte von Behältern."
)


def _cloud_describe(image_path: str, prompt: str) -> str | None:
    """Free-form image description via the cloud VLM (no object parsing)."""
    from backend.core.config import config

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    url = _cloud_chat_completions_url()
    headers = {
        "Authorization": f"Bearer {config.CLOUD_API_KEY}",
        "Content-Type": "application/json",
    }
    locate_model = getattr(config, "LOCATE_CLOUD_MODEL", "").strip()
    models = [m for m in [locate_model, config.CLOUD_MODEL] if m]
    seen: set[str] = set()
    models = [m for m in models if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]
    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            "max_tokens": 150,
            "temperature": 0.2,
        }
        # Retry on 429 (free-tier per-minute rate limit) with a short backoff
        # before giving up on this model and falling to local.
        for attempt in range(3):
            resp = http_post(url, json=payload, headers=headers, timeout=20.0)
            if resp.status_code == 429:
                wait = 3.0 * (attempt + 1)
                log.warning("recognize: cloud 429 rate-limited (%s), retrying in %.0fs", model, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                log.warning("recognize: cloud %s -> %s: %s", model, resp.status_code, resp.text[:200])
                break
            return resp.json()["choices"][0]["message"]["content"].strip()
    return None


def describe_scene(image_path: str, de: bool = False, prompt: str | None = None) -> str | None:
    """Open-vocabulary description of whatever the camera sees.

    Recognizes ANY object/person/animal via the vision LLM. Ollama (offline)
    first, then cloud. Returns None if no VLM is configured (caller falls back to
    the on-board 80-class detector). ``prompt`` overrides the default (e.g. an
    appearance-focused prompt for "what am I wearing").
    """
    if prompt is None:
        prompt = _RECOGNIZE_PROMPT_DE if de else _RECOGNIZE_PROMPT_EN

    # Cloud vision FIRST when available — a hosted VL model (e.g. qwen2.5-VL-72B)
    # is far more accurate and faster than a small local model on CPU. Falls back
    # to local Ollama if the cloud call fails, so you stay offline-capable.
    if _cloud_vision_available():
        try:
            text = _cloud_describe(image_path, prompt)
            if text:
                return text
        except Exception as e:
            log.warning("recognize: cloud describe failed (%s) — trying local", e)

    if _ollama_vision_available():
        try:
            from backend.core.config import config
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            base = config.OLLAMA_BASE_URL.rstrip("/")
            # Try the chosen model, then lighter fallbacks if it errors/blanks.
            for i, model in enumerate(_ollama_vision_models()):
                try:
                    for p in (prompt, _DESCRIBE_PROMPT_DE if de else _DESCRIBE_PROMPT_EN):
                        text = _ollama_generate(base, model, p, b64)
                        if text:
                            if i > 0:
                                log.info("recognize: used fallback vision model %s", model)
                            return text
                except Exception as e:
                    log.warning("recognize: model %s failed (%s) — trying fallback", model, e)
                    continue
        except Exception as e:
            log.warning("recognize: ollama describe failed: %s", e)

    return None


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
    if _cloud_vision_available() or _ollama_vision_available() or _cli_available():
        return True
    # Object memory alone (no VLM) can still find items you've taught Plasma.
    try:
        from backend.modules.vision import object_memory
        return object_memory.is_available() and bool(object_memory.list_objects())
    except Exception:
        return False


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
        if getattr(config, "CAMERA_AUTO_WHITE_BALANCE", False):
            from backend.modules.vision.capture import apply_gray_world
            frame = apply_gray_world(frame)   # opt-in software colour correction
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

    # Personal object memory: if this is an item you taught Plasma ("remember
    # this as my keys"), pin the EXACT one by embedding match and answer directly
    # — faster and specific, no VLM round-trip.
    try:
        enrolled_reply = _try_enrolled_object(frame.copy(), obj, img_w, img_h, de)
        if enrolled_reply:
            return enrolled_reply
    except Exception as e:
        log.debug("locate: enrolled-object step skipped: %s", e)

    # Otherwise, try to pin the object to a box via the class detector (80 classes).
    # Draw on a copy so the JPEG already written for the vision tiers is untouched.
    try:
        annotated = _annotate_object(frame.copy(), obj)
        if annotated:
            _set_last_annotated(annotated)
    except Exception as e:
        log.debug("locate: annotation step skipped: %s", e)

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

        # No vision model configured — object memory is the only backend, and
        # this item either isn't taught yet or wasn't in view.
        if not (_cloud_vision_available() or _ollama_vision_available() or _cli_available()):
            return (
                f"Ich kann {obj} gerade nicht sehen. Zeig es mir und sag "
                f"'Merke dir das als {obj}', dann finde ich es wieder."
                if de else
                f"I can't see your {obj} right now. Show it to me and say "
                f"'remember this as {obj}', then I'll find it. (For finding anything, "
                f"set LOCATE_VISION_OLLAMA_MODEL=moondream.)"
            )
        err_str = str(last_err) if last_err else "no backend available"
        return f"Suche fehlgeschlagen: {err_str}" if de else f"Search failed: {err_str}"
    finally:
        try:
            Path(img_path).unlink(missing_ok=True)
        except Exception:
            pass


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
