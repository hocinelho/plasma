"""Image generation skill via Muapi.ai (the Open-Generative-AI backend).

"generate an image of a sunset over mountains" → returns a hosted image URL.

Setup:
  1. Get an access key at https://muapi.ai
  2. Add to .env:
       MUAPI_API_KEY=your_key_here
       MUAPI_IMAGE_MODEL=flux-schnell   # or any model endpoint slug muapi exposes

API contract (from Open-Generative-AI):
  POST {base}/api/v1/{model}    headers: x-api-key   body: {"prompt": "..."}
       → {"request_id": "..."}
  GET  {base}/api/v1/predictions/{request_id}/result
       → {"status": "completed", "outputs": ["https://...png"]}   (poll until done)
"""
from __future__ import annotations
import logging
import re
import time

from backend.core.http_client import get as http_get
from backend.core.http_client import post as http_post

log = logging.getLogger("plasma.skill.image_gen")

META = {
    "name": "image_gen",
    "description": "Generate an image from a text description using AI.",
    "triggers": [
        # English
        "generate an image",
        "generate a picture",
        "generate image",
        "create an image",
        "create a picture",
        "make an image",
        "make a picture",
        "draw me",
        "draw a",
        "draw an",
        "paint a",
        "generate a photo",
        "create a photo",
        # German
        "generiere ein bild",
        "erstelle ein bild",
        "mach ein bild",
        "male ein",
        "zeichne ein",
        "erzeuge ein bild",
    ],
    "example_utterances": [
        "Generate an image of a sunset over the ocean",
        "Draw a cat wearing a hat",
        "Create a picture of a futuristic city",
        "Generiere ein Bild von einem Berg",
    ],
}

_PROMPT_RE = re.compile(
    r"(?:generate|create|make|draw|paint|erstelle|generiere|mach|male|zeichne|erzeuge)\s+"
    r"(?:me\s+)?(?:an?\s+|ein(?:en|e)?\s+)?(?:image|picture|photo|bild|foto)?\s*"
    r"(?:of|von|showing|mit|:)?\s*(.+?)(?:\s*[.?!]|$)",
    re.I,
)


def _is_available() -> bool:
    from backend.core.config import config
    return bool(config.MUAPI_API_KEY.strip())


def _extract_prompt(utterance: str) -> str | None:
    m = _PROMPT_RE.search(utterance)
    if not m:
        return None
    prompt = m.group(1).strip().rstrip(".,!?")
    # Reject leftover filler like "an image" with no subject
    if not prompt or prompt.lower() in {"image", "picture", "photo", "bild", "foto"}:
        return None
    return prompt


def _extract_url(result: dict) -> str | None:
    """Muapi result shapes vary; pull the first image/video URL we can find."""
    for key in ("outputs", "output", "images", "urls"):
        val = result.get(key)
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url") or first.get("image_url")
        if isinstance(val, str):
            return val
    # Sometimes nested under "data"
    data = result.get("data")
    if isinstance(data, dict):
        return _extract_url(data)
    return None


def _generate(prompt: str) -> str | None:
    """Submit + poll Muapi.ai. Returns an image URL or None."""
    from backend.core.config import config

    base = config.MUAPI_BASE_URL.rstrip("/")
    headers = {"x-api-key": config.MUAPI_API_KEY, "Content-Type": "application/json"}

    submit = http_post(
        f"{base}/api/v1/{config.MUAPI_IMAGE_MODEL}",
        json={"prompt": prompt},
        headers=headers,
        timeout=30.0,
    )
    submit.raise_for_status()
    body = submit.json()
    request_id = body.get("request_id") or body.get("id")
    if not request_id:
        # Some models return the URL synchronously
        url = _extract_url(body)
        if url:
            return url
        raise RuntimeError("No request_id returned by Muapi.")

    deadline = time.monotonic() + config.MUAPI_TIMEOUT
    poll_url = f"{base}/api/v1/predictions/{request_id}/result"
    while time.monotonic() < deadline:
        resp = http_get(poll_url, headers=headers, timeout=15.0)
        resp.raise_for_status()
        result = resp.json()
        status = (result.get("status") or "").lower()
        if status in ("completed", "succeeded", "success"):
            return _extract_url(result)
        if status in ("failed", "error"):
            raise RuntimeError(f"Generation failed: {result.get('error', 'unknown error')}")
        time.sleep(2.0)

    raise TimeoutError("Image generation timed out.")


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    if not _is_available():
        return (
            "Bildgenerierung ist nicht eingerichtet. Setze MUAPI_API_KEY in der .env."
            if de
            else "Image generation isn't set up. Add MUAPI_API_KEY to your .env."
        )

    prompt = _extract_prompt(utterance)
    if not prompt:
        return (
            "Was soll ich malen? Sag z.B. 'Generiere ein Bild von einem Sonnenuntergang'."
            if de
            else "What should I create? Try 'generate an image of a sunset'."
        )

    try:
        url = _generate(prompt)
    except TimeoutError:
        return (
            "Die Bildgenerierung hat zu lange gedauert."
            if de
            else "The image generation took too long."
        )
    except Exception as e:
        log.warning("image generation failed: %s", e)
        return (
            f"Bildgenerierung fehlgeschlagen: {e}"
            if de
            else f"Image generation failed: {e}"
        )

    if not url:
        return (
            "Ich habe kein Bild zurückbekommen."
            if de
            else "I didn't get an image back."
        )

    if de:
        return f"Hier ist dein Bild von {prompt}: {url}"
    return f"Here's your image of {prompt}: {url}"


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
