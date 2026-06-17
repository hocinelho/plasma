"""Alarm clock skill — persistent alarms stored in .plasma/alarms.json.

Fires proactive TTS when an alarm triggers. Supports multi-step flow:
  User: "set alarm"  → Plasma: "What time?"
  User: "7am"        → Plasma: "Alarm set for 7:00 AM."

EN + DE supported.
"""
from __future__ import annotations
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("plasma.skill.alarm")

_ALARM_FILE = Path(__file__).resolve().parents[2] / ".plasma" / "alarms.json"

META = {
    "name": "alarm",
    "description": "Set, list, and cancel alarms that trigger spoken alerts.",
    "triggers": [
        # English
        "set an alarm",
        "set alarm",
        "wake me up",
        "alarm at",
        "alarm for",
        "cancel alarm",
        "list alarms",
        "show alarms",
        "what alarms",
        "delete alarm",
        # German
        "wecker stellen",
        "weck mich um",
        "wecker für",
        "wecker setzen",
        "alarm stellen",
        "wecker canceln",
        "wecker löschen",
        "zeig meine wecker",
    ],
    "example_utterances": [
        "Set an alarm for 7am",
        "Wake me up at 6:30",
        "Cancel alarm",
        "List alarms",
        "Wecker stellen für 8 Uhr",
    ],
}

_TIME_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|uhr)?",
    re.I,
)
_ALARM_CMD = re.compile(
    r"(?:set\s+(?:an\s+)?alarm|wake\s+me\s+up|alarm\s+(?:at|for)|"
    r"wecker\s+(?:stellen|für|setzen|um)|weck\s+mich\s+um|alarm\s+stellen)",
    re.I,
)
_CANCEL = re.compile(r"(?:cancel|delete|remove|löschen|canceln)\s+(?:all\s+)?alarm|wecker", re.I)
_LIST = re.compile(r"(?:list|show|what)\s+alarm|zeig\s+(?:meine\s+)?wecker", re.I)

_PENDING_INTENT_CAT = "pending_intent"
_PENDING_INTENT_CONTENT = "alarm:awaiting_time"


def _load() -> list[dict]:
    try:
        if _ALARM_FILE.exists():
            return json.loads(_ALARM_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed to load alarms: %s", e)
    return []


def _save(alarms: list[dict]) -> None:
    try:
        _ALARM_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ALARM_FILE.write_text(json.dumps(alarms, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("Failed to save alarms: %s", e)


def _parse_time(utterance: str) -> datetime | None:
    m = _TIME_RE.search(utterance)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif ampm == "uhr" or (not ampm and hour < 7):
        # Assume 24h if no am/pm and hour < 7 (e.g. "1" → 13:00 would be odd at 1am for most)
        pass

    if hour > 23 or minute > 59:
        return None

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _fire_alarm(alarm_time_iso: str, label: str, language: str) -> None:
    target = datetime.fromisoformat(alarm_time_iso)
    delay = (target - datetime.now()).total_seconds()
    if delay > 0:
        time.sleep(delay)

    # Remove from persistent list
    alarms = _load()
    alarms = [a for a in alarms if a.get("time") != alarm_time_iso]
    _save(alarms)

    msg = f"Wecker! {label}" if language == "de" else f"Alarm! {label}"
    log.info("Alarm fired: %s", msg)
    try:
        from backend.modules.voice.proactive_tts import proactive_tts
        proactive_tts.fire(msg, language)
    except Exception as e:
        log.warning("Alarm proactive TTS failed: %s", e)
        print(f"\n🔔 ALARM: {msg}\n", flush=True)


def _schedule_alarm(target: datetime, label: str, language: str) -> None:
    t = threading.Thread(
        target=_fire_alarm,
        args=(target.isoformat(), label, language),
        daemon=True,
        name=f"plasma-alarm-{target.strftime('%H%M')}",
    )
    t.start()


def _set_pending(session_id: str, language: str) -> str:
    """Store pending intent so the next user turn is routed back here."""
    try:
        from backend.modules.router.chat_service import get_memory
        mem = get_memory()
        # Clear any old pending alarm intent for this session
        old = mem.get_facts(category=_PENDING_INTENT_CAT)
        for f in old:
            if f.get("content", "").startswith("alarm:"):
                mem.delete_fact(f["id"])
        mem.add_fact(
            category=_PENDING_INTENT_CAT,
            content=_PENDING_INTENT_CONTENT,
            confidence=1.0,
            source="alarm_skill",
            user=session_id,
        )
    except Exception as e:
        log.warning("Failed to set pending intent: %s", e)
    return "Um wie viel Uhr?" if language == "de" else "What time?"


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").strip()
    language = (args or {}).get("language", "en")
    session_id = (args or {}).get("session_id", "default")
    de = language == "de"

    # List alarms
    if _LIST.search(utterance):
        alarms = _load()
        if not alarms:
            return "Keine Wecker gesetzt." if de else "No alarms set."
        items = [f"{a['label']} um {datetime.fromisoformat(a['time']).strftime('%H:%M')}" if de
                 else f"{a['label']} at {datetime.fromisoformat(a['time']).strftime('%I:%M %p').lstrip('0')}"
                 for a in alarms]
        return ("Wecker: " if de else "Alarms: ") + "; ".join(items) + "."

    # Cancel all
    if _CANCEL.search(utterance):
        _save([])
        return "Alle Wecker gelöscht." if de else "All alarms cancelled."

    # Set alarm — try to extract time from this utterance
    if _ALARM_CMD.search(utterance):
        target = _parse_time(utterance)
        if target:
            label = "Wecker" if de else "Alarm"
            alarms = _load()
            alarms.append({"time": target.isoformat(), "label": label, "language": language})
            _save(alarms)
            _schedule_alarm(target, label, language)
            fmt = target.strftime("%H:%M") if de else target.strftime("%I:%M %p").lstrip("0")
            return f"Wecker gestellt für {fmt}." if de else f"Alarm set for {fmt}."
        # No time found — ask
        return _set_pending(session_id, language)

    # Check if this is a pending-intent reply (just a time, e.g. "7am")
    target = _parse_time(utterance)
    if target:
        label = "Wecker" if de else "Alarm"
        alarms = _load()
        alarms.append({"time": target.isoformat(), "label": label, "language": language})
        _save(alarms)
        _schedule_alarm(target, label, language)
        fmt = target.strftime("%H:%M") if de else target.strftime("%I:%M %p").lstrip("0")
        return f"Wecker gestellt für {fmt}." if de else f"Alarm set for {fmt}."

    return (
        "Sag z.B. 'Wecker stellen für 7 Uhr' oder 'Wecker löschen'."
        if de
        else "Try: 'set alarm for 7am', 'list alarms', or 'cancel alarm'."
    )


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
