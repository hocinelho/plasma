"""Smart home control via Home Assistant REST API (English + German).

Setup:
  1. Install Home Assistant: https://www.home-assistant.io/
  2. Create a Long-Lived Access Token: Profile → Long-Lived Access Tokens
  3. Add to .env:
       HA_BASE_URL=http://homeassistant.local:8123
       HA_TOKEN=your_long_lived_token
       HA_LIGHT_ENTITY=light.all   # or light.living_room, etc.
"""
from __future__ import annotations
import logging
import re

from backend.core.config import config
from backend.core.http_client import get as http_get
from backend.core.http_client import post as http_post

log = logging.getLogger("plasma.skill.smart_home")

META = {
    "name": "smart_home",
    "description": "Control smart home devices (lights, switches) via Home Assistant.",
    "triggers": [
        # Lights — English
        "turn on the lights",
        "turn off the lights",
        "lights on",
        "lights off",
        "switch on the lights",
        "switch off the lights",
        "dim the lights",
        "brighten the lights",
        "set the lights",
        "is the light on",
        "is the light off",
        "are the lights on",
        "are the lights off",
        "turn on the light",
        "turn off the light",
        # Generic device — English
        "turn on the",
        "turn off the",
        "switch on",
        "switch off",
        # Scenes — English
        "activate movie mode",
        "activate night mode",
        "activate reading mode",
        "movie mode",
        "night mode",
        "reading mode",
        "party mode",
        "morning mode",
        # Scenes — German
        "film modus aktivieren",
        "nacht modus aktivieren",
        "lese modus aktivieren",
        # Lights — German
        "schalte das licht ein",
        "schalte das licht aus",
        "licht einschalten",
        "licht ausschalten",
        "licht an",
        "licht aus",
        "mach das licht an",
        "mach das licht aus",
        "mach das licht dunkler",
        "mach das licht heller",
        "ist das licht an",
        "sind die lichter an",
    ],
    "example_utterances": [
        "Turn on the lights",
        "Turn off the bedroom lights",
        "Dim the lights",
        "Is the light on?",
        "Schalte das Licht ein",
        "Mach das Licht aus",
    ],
}

# Room name → HA-style suffix (appended to domain, e.g. "light.living_room")
_ROOMS: dict[str, str] = {
    "living room": "living_room",
    "bedroom": "bedroom",
    "kitchen": "kitchen",
    "bathroom": "bathroom",
    "office": "office",
    "hallway": "hallway",
    "garage": "garage",
    "wohnzimmer": "living_room",
    "schlafzimmer": "bedroom",
    "küche": "kitchen",
    "bad": "bathroom",
    "badezimmer": "bathroom",
    "büro": "office",
    "flur": "hallway",
}

# Words that indicate ON action
_ON_WORDS = re.compile(
    r"\b(turn on|switch on|lights? on|licht (ein|an)|einschalten|"
    r"mach.* an|heller|brighten)\b", re.I
)
# Words that indicate OFF action
_OFF_WORDS = re.compile(
    r"\b(turn off|switch off|lights? off|licht aus|ausschalten|"
    r"mach.* aus)\b", re.I
)
# Words that indicate DIM action
_DIM_WORDS = re.compile(r"\b(dim|dunkler|dimm)\b", re.I)
# Words that indicate STATE QUERY
_STATE_WORDS = re.compile(
    r"\b(is (the|das) lights? (on|off|an|aus)|are the lights|ist das licht)\b", re.I
)
# Words that indicate SCENE activation
_SCENE_WORDS = re.compile(
    r"\b(activate|turn on|start|enable|aktiviere|starte)\b.+\b(mode|scene|szene|modus)\b"
    r"|\b(movie mode|night mode|reading mode|party mode|morning mode|"
    r"film modus|nacht modus|lese modus|party modus|morgen modus)\b",
    re.I,
)
_SCENE_NAMES: dict[str, str] = {
    "movie": "movie_mode", "film": "movie_mode",
    "night": "night_mode", "nacht": "night_mode",
    "reading": "reading_mode", "lesen": "reading_mode", "lese": "reading_mode",
    "party": "party_mode",
    "morning": "morning_mode", "morgen": "morning_mode",
    "day": "day_mode", "tag": "day_mode",
    "relax": "relax_mode", "entspannen": "relax_mode",
}


def _is_available() -> bool:
    return bool(config.HA_TOKEN.strip())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }


def _entity_for_utterance(utterance: str) -> str:
    """Resolve the best entity_id from the utterance, falling back to config default."""
    lower = utterance.lower()
    for room_phrase, room_slug in _ROOMS.items():
        if room_phrase in lower:
            return f"light.{room_slug}"
    return config.HA_LIGHT_ENTITY


def _call_service(domain: str, service: str, entity_id: str, extra: dict | None = None) -> bool:
    url = f"{config.HA_BASE_URL.rstrip('/')}/api/services/{domain}/{service}"
    payload: dict = {"entity_id": entity_id}
    if extra:
        payload.update(extra)
    try:
        resp = http_post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        return True
    except Exception as e:
        log.warning(f"HA service call failed ({domain}.{service}): {e}")
        return False


def _get_state(entity_id: str) -> str | None:
    url = f"{config.HA_BASE_URL.rstrip('/')}/api/states/{entity_id}"
    try:
        resp = http_get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json().get("state")
    except Exception as e:
        log.warning(f"HA state read failed ({entity_id}): {e}")
        return None


def run(args: dict | None = None) -> str:

    if not _is_available():
        return (
            "Smart home is not configured. "
            "Add HA_BASE_URL and HA_TOKEN to your .env file."
        )

    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    entity_id = _entity_for_utterance(utterance)
    domain = entity_id.split(".")[0] if "." in entity_id else "light"

    # Scene activation
    if _SCENE_WORDS.search(utterance):
        scene_id: str | None = None
        lower = utterance.lower()
        for keyword, scene in _SCENE_NAMES.items():
            if keyword in lower:
                scene_id = scene
                break
        if scene_id:
            ok = _call_service("scene", "turn_on", f"scene.{scene_id}")
            if language == "de":
                return f"Szene '{scene_id}' aktiviert." if ok else f"Konnte Szene '{scene_id}' nicht aktivieren."
            return f"Scene '{scene_id}' activated." if ok else f"Couldn't activate scene '{scene_id}'."
        return "Which scene? Try: 'activate movie mode', 'night mode', or 'reading mode'."

    # State query
    if _STATE_WORDS.search(utterance):
        state = _get_state(entity_id)
        if state is None:
            return "I couldn't reach Home Assistant." if language != "de" else "Ich konnte Home Assistant nicht erreichen."
        if language == "de":
            return f"Das Licht ist {'an' if state == 'on' else 'aus'}."
        return f"The light is {state}."

    # Dim
    if _DIM_WORDS.search(utterance):
        ok = _call_service(domain, "turn_on", entity_id, {"brightness_pct": 30})
        if language == "de":
            return "Licht gedimmt." if ok else "Konnte das Licht nicht dimmen."
        return "Lights dimmed." if ok else "Couldn't dim the lights."

    # Turn on
    if _ON_WORDS.search(utterance):
        ok = _call_service(domain, "turn_on", entity_id)
        if language == "de":
            return "Licht eingeschaltet." if ok else "Konnte das Licht nicht einschalten."
        return "Lights on." if ok else "Couldn't turn the lights on."

    # Turn off
    if _OFF_WORDS.search(utterance):
        ok = _call_service(domain, "turn_off", entity_id)
        if language == "de":
            return "Licht ausgeschaltet." if ok else "Konnte das Licht nicht ausschalten."
        return "Lights off." if ok else "Couldn't turn the lights off."

    return (
        "Try: 'turn on the lights', 'turn off the bedroom lights', or 'dim the lights'."
        if language != "de"
        else "Versuch: 'Licht an', 'Licht aus' oder 'Mach das Licht dunkler'."
    )


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
