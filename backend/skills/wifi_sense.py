"""WiFi presence sensing via RuView — "is anyone home?", "who's in the kitchen?".

RuView (https://github.com/hocinelho/RuView) turns WiFi Channel State Information
into spatial sensing: it detects people through walls, counts occupants, and maps
rooms — no cameras. It runs on its own hardware (ESP32-S3, RPi + nexmon_csi, or a
research NIC) or the no-hardware Docker demo, and exposes an HTTP API.

Plasma is the VOICE LAYER on top: this skill queries RuView and answers presence
questions. It degrades gracefully — if RuView isn't set up, it explains how.

Setup:
  # Quick demo (no hardware):
  #   docker run -p 3000:3000 ruvnet/wifi-densepose:latest
  # then in .env:
  RUVIEW_ENABLED=true
  RUVIEW_URL=http://localhost:3000
  # RUVIEW_API_KEY=...   # if your instance requires one

The RuView HTTP shape varies by version, so we probe a few common endpoints and
parse the JSON flexibly (looking for presence / count / rooms), rather than
hard-coding one path.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from backend.core.config import config
from backend.core.http_client import get as http_get

log = logging.getLogger("plasma.skill.wifi_sense")

META = {
    "name": "wifi_sense",
    "description": "WiFi-based presence sensing via RuView (people/rooms, no camera).",
    "triggers": [
        # English
        "is anyone home",
        "is someone home",
        "anybody home",
        "who is around",
        "who's around",
        "who is in the",
        "who's in the",
        "is anyone in the",
        "is someone in the",
        "anyone in the",
        "how many people are home",
        "how many people are in the house",
        "people around",
        "scan the house",
        "wifi presence",
        "sense the room",
        "is the house empty",
        # Proactive alert toggle — English
        "watch the house",
        "alert me when someone",
        "tell me when someone comes home",
        "tell me when someone enters",
        "let me know when someone",
        "stop watching the house",
        "stop house alerts",
        # German
        "beobachte das haus",
        "sag mir wenn jemand kommt",
        "hör auf das haus zu beobachten",
        "ist jemand zu hause",
        "ist jemand da",
        "wer ist im",
        "wer ist zu hause",
        "wie viele leute sind zu hause",
        "ist jemand im",
        "scanne das haus",
    ],
    "example_utterances": [
        "Is anyone home?",
        "Who's in the living room?",
        "How many people are home?",
        "Ist jemand zu Hause?",
    ],
}

# Candidate endpoints across RuView versions (first that returns JSON wins).
_ENDPOINTS = ("/api/presence", "/presence", "/api/status", "/status", "/api/sensors")

_ROOM_RE = re.compile(r"in the ([a-zA-Zà-ÿ ]+?)(?:[.?!]|$)|im ([a-zA-Zà-ÿ ]+?)(?:[.?!]|$)", re.I)


def _extract_room(utterance: str) -> Optional[str]:
    m = _ROOM_RE.search(utterance or "")
    if not m:
        return None
    room = (m.group(1) or m.group(2) or "").strip().lower()
    return room or None


def is_available() -> bool:
    return bool(getattr(config, "RUVIEW_ENABLED", False))


def _headers() -> dict:
    key = getattr(config, "RUVIEW_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _query_ruview() -> Optional[dict]:
    """Return RuView's latest reading as a dict, or None if unreachable."""
    base = getattr(config, "RUVIEW_URL", "").rstrip("/")
    if not base:
        return None
    for ep in _ENDPOINTS:
        try:
            resp = http_get(f"{base}{ep}", headers=_headers(), timeout=4.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return None


def _interpret(data: dict, room: Optional[str], de: bool) -> str:
    """Turn RuView's (loosely-shaped) JSON into a spoken answer."""
    # Total occupancy: try the common key names.
    count = None
    for k in ("count", "people", "occupancy", "persons", "num_people", "total"):
        v = data.get(k)
        if isinstance(v, (int, float)):
            count = int(v)
            break
    present = data.get("present")
    if count is None and isinstance(present, bool):
        count = 1 if present else 0

    # Per-room breakdown, if present.
    rooms = data.get("rooms") or data.get("areas") or {}
    if room and isinstance(rooms, dict):
        # Find a matching room key (fuzzy).
        match = next((rooms[k] for k in rooms if room in k.lower() or k.lower() in room), None)
        if match is not None:
            n = match.get("count") if isinstance(match, dict) else match
            n = int(n) if isinstance(n, (int, float)) else (1 if match else 0)
            if de:
                return f"Im {room} sind gerade {n} Person(en)." if n else f"Im {room} ist niemand."
            return f"There {'is' if n == 1 else 'are'} {n} in the {room}." if n else f"No one is in the {room}."

    if count is None:
        # We reached RuView but couldn't parse it — be honest.
        return (
            "Ich habe den WiFi-Sensor erreicht, konnte die Antwort aber nicht deuten."
            if de else
            "I reached the WiFi sensor but couldn't read its response format."
        )
    if count <= 0:
        return "Es scheint niemand zu Hause zu sein." if de else "No one seems to be home."
    if de:
        return f"Ich spüre {count} Person(en) zu Hause." if count > 1 else "Ich spüre eine Person zu Hause."
    return f"I sense {count} people at home." if count > 1 else "I sense one person at home."


_STOP_ALERTS_RE = re.compile(r"\b(stop|hör auf|disable|no more)\b", re.I)
_START_ALERTS_RE = re.compile(
    r"\b(watch the house|alert me when|tell me when someone|let me know when someone"
    r"|beobachte das haus|sag mir wenn jemand)\b",
    re.I,
)


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    de = language == "de"

    if not is_available():
        return (
            "WiFi-Sensing (RuView) ist nicht aktiviert. Starte RuView (z.B. die "
            "Docker-Demo) und setze RUVIEW_ENABLED=true und RUVIEW_URL in der .env."
            if de else
            "WiFi sensing (RuView) isn't set up. It reads people from WiFi signals — "
            "run RuView (e.g. its Docker demo: docker run -p 3000:3000 "
            "ruvnet/wifi-densepose:latest), then set RUVIEW_ENABLED=true and "
            "RUVIEW_URL in your .env. Real through-wall sensing needs an ESP32-S3 (~$9)."
        )

    # Proactive alert toggle ("watch the house" / "stop watching the house").
    if _STOP_ALERTS_RE.search(utterance) and "watch" in utterance.lower() \
            or ("stop" in utterance.lower() and "house" in utterance.lower()):
        try:
            from backend.modules.sense.ruview_monitor import ruview_monitor
            ruview_monitor.stop_watching()
        except Exception as e:
            log.warning("stop alerts failed: %s", e)
        return "Ich beobachte das Haus nicht mehr." if de else "I'll stop watching the house."
    if _START_ALERTS_RE.search(utterance):
        try:
            from backend.modules.sense.ruview_monitor import ruview_monitor
            ok = ruview_monitor.start_watching(language)
        except Exception as e:
            log.warning("start alerts failed: %s", e)
            ok = False
        if ok:
            return (
                "Okay, ich beobachte das Haus und sage Bescheid, wenn jemand kommt oder geht."
                if de else
                "Okay — I'll watch the house and tell you when someone comes or goes."
            )
        return (
            "Dafür muss RuView laufen (RUVIEW_ENABLED=true)."
            if de else
            "I need RuView running for that (set RUVIEW_ENABLED=true)."
        )

    data = _query_ruview()
    if data is None:
        return (
            f"Ich kann den WiFi-Sensor unter {config.RUVIEW_URL} nicht erreichen. "
            "Läuft RuView?"
            if de else
            f"I can't reach the WiFi sensor at {config.RUVIEW_URL}. Is RuView running?"
        )

    return _interpret(data, _extract_room(utterance), de)


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
