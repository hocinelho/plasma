"""
RuView presence monitor — background WiFi-sensing alerts.

Polls the RuView HTTP API on a daemon thread and fires spoken ProactiveTTS
alerts when presence changes:
  • someone arrives ("Someone just entered the house.")
  • a specific room becomes occupied ("Someone entered the living room.")
  • the house empties ("The house is empty now.")

Optional: a no-op unless RUVIEW_ENABLED=true. Mirrors WakeMonitor/VisionMonitor
(daemon thread → proactive_tts.fire), so it never blocks the event loop.
Reuses the endpoint-probing + flexible parsing from the wifi_sense skill.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from backend.core.config import config
from backend.modules.voice.proactive_tts import proactive_tts

log = logging.getLogger("plasma.sense.ruview_monitor")


def _reading_counts(data: dict) -> tuple[Optional[int], dict[str, int]]:
    """Extract (total_count, {room: count}) from a RuView reading, best-effort."""
    total = None
    for k in ("count", "people", "occupancy", "persons", "num_people", "total"):
        v = data.get(k)
        if isinstance(v, (int, float)):
            total = int(v)
            break
    if total is None and isinstance(data.get("present"), bool):
        total = 1 if data["present"] else 0

    rooms: dict[str, int] = {}
    raw_rooms = data.get("rooms") or data.get("areas") or {}
    if isinstance(raw_rooms, dict):
        for name, val in raw_rooms.items():
            if isinstance(val, dict):
                n = val.get("count", 1 if val.get("present") else 0)
            elif isinstance(val, bool):
                n = 1 if val else 0
            else:
                n = val
            if isinstance(n, (int, float)):
                rooms[str(name)] = int(n)
    if total is None and rooms:
        total = sum(rooms.values())
    return total, rooms


class RuViewMonitor:
    """Singleton background poller that announces presence changes."""

    def __init__(self) -> None:
        self.enabled = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._language = "en"
        self._poll_s = 5.0
        self._cooldown_s = 30.0

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Boot-time auto-start: only if RUVIEW_ALERTS=true in .env."""
        if not getattr(config, "RUVIEW_ENABLED", False) or not getattr(config, "RUVIEW_ALERTS", False):
            log.info("RuView alerts disabled — monitor not started")
            return
        self.start_watching()

    async def stop(self) -> None:
        self.stop_watching()

    # Sync variants so a voice skill can toggle alerts at runtime.
    def start_watching(self, language: str = "en") -> bool:
        """Begin polling; returns False if RuView isn't enabled/reachable-config."""
        if not getattr(config, "RUVIEW_ENABLED", False):
            return False
        with self._lock:
            self._language = language
            if self._thread and self._thread.is_alive():
                return True
            self._poll_s = float(getattr(config, "RUVIEW_POLL_S", 5.0))
            self._cooldown_s = float(getattr(config, "RUVIEW_ALERT_COOLDOWN_S", 30.0))
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="plasma-ruview-monitor")
            self._thread.start()
            self.enabled = True
            log.info("RuViewMonitor watching (poll=%.1fs)", self._poll_s)
            return True

    def stop_watching(self) -> None:
        with self._lock:
            self._stop_event.set()
            self.enabled = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3.0)
            self._thread = None

    # ── internals ─────────────────────────────────────────────────────────

    def _poll(self) -> Optional[dict]:
        from backend.core.http_client import get as http_get
        base = getattr(config, "RUVIEW_URL", "").rstrip("/")
        key = getattr(config, "RUVIEW_API_KEY", "").strip()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        for ep in ("/api/presence", "/presence", "/api/status", "/status", "/api/sensors"):
            try:
                resp = http_get(f"{base}{ep}", headers=headers, timeout=4.0)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
        return None

    def _announce(self, text: str) -> None:
        log.info("RuView alert: %s", text)
        proactive_tts.fire(text, self._language)

    def _loop(self) -> None:
        de = self._language == "de"
        prev_total: Optional[int] = None
        prev_rooms: dict[str, int] = {}
        last_alert = 0.0

        while not self._stop_event.is_set():
            data = self._poll()
            if data is not None:
                total, rooms = _reading_counts(data)
                now = time.time()
                cooled = (now - last_alert) >= self._cooldown_s

                if total is not None and prev_total is not None and cooled:
                    # House-level arrival / emptied.
                    if prev_total == 0 and total > 0:
                        self._announce(
                            "Es ist jemand nach Hause gekommen." if de
                            else "Someone just arrived home."
                        )
                        last_alert = now
                    elif prev_total > 0 and total == 0:
                        self._announce(
                            "Das Haus ist jetzt leer." if de else "The house is empty now."
                        )
                        last_alert = now
                    else:
                        # Per-room entry (only if we have room-level data).
                        for room, n in rooms.items():
                            if n > 0 and prev_rooms.get(room, 0) == 0 and cooled:
                                self._announce(
                                    f"Jemand hat das {room} betreten." if de
                                    else f"Someone entered the {room}."
                                )
                                last_alert = now
                                break

                if total is not None:
                    prev_total = total
                if rooms:
                    prev_rooms = rooms

            self._stop_event.wait(self._poll_s)


# Module-level singleton — imported by main.py
ruview_monitor = RuViewMonitor()
