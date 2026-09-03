"""
Proactive TTS broadcaster — fires spoken alerts to all connected WS clients.

Background threads call `proactive_tts.fire(text, language)`.
The message is synthesized (via Piper, if enabled) and pushed as base64 audio
to every browser connected on /ws/alerts.

Architecture mirrors WakeMonitor: thread → asyncio.Queue → broadcast_loop → ws.send_json.
"""
from __future__ import annotations
import asyncio
import base64
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

log = logging.getLogger("plasma.proactive_tts")


class ProactiveTTS:
    """Singleton: accepts fire() from any thread, broadcasts to /ws/alerts clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        log.info("ProactiveTTS started")

    async def stop(self) -> None:
        if self._broadcast_task:
            self._broadcast_task.cancel()

    # ── client management ────────────────────────────────────────────────

    def add_client(self, ws: WebSocket) -> None:
        self.clients.add(ws)
        log.debug(f"Alert WS client added (total={len(self.clients)})")

    def remove_client(self, ws: WebSocket) -> None:
        self.clients.discard(ws)
        log.debug(f"Alert WS client removed (total={len(self.clients)})")

    # ── public API (thread-safe) ─────────────────────────────────────────

    def fire(self, text: str, language: str = "en", gesture: str | None = None) -> None:
        """Call from any thread to push an alert to all WS clients.

        `gesture` is an optional avatar_state gesture name (e.g. "handup") —
        the browser plays it alongside the spoken text. Used for reactions
        that are more than just an announcement, such as waving back when a
        raised hand is seen on camera.
        """
        if self._loop is None or self._queue is None:
            log.warning("ProactiveTTS not started — alert dropped: %s", text)
            return
        asyncio.run_coroutine_threadsafe(
            self._queue.put({"text": text, "language": language, "gesture": gesture}),
            self._loop,
        )

    # ── internals ────────────────────────────────────────────────────────

    async def _broadcast_loop(self) -> None:
        while True:
            item = await self._queue.get()
            text = item["text"]
            language = item.get("language", "en")
            gesture = item.get("gesture")

            audio_b64: str | None = None
            try:
                from backend.core.config import config
                if config.TTS_ENABLED:
                    from backend.modules.voice.tts import synthesize as tts_synthesize
                    wav = await asyncio.to_thread(tts_synthesize, text, language)
                    if wav:
                        audio_b64 = base64.b64encode(wav).decode("ascii")
            except Exception as e:
                log.warning("ProactiveTTS synthesis failed: %s", e)

            payload = {"type": "alert", "text": text, "audio_b64": audio_b64, "gesture": gesture}
            dead: set[WebSocket] = set()
            for ws in list(self.clients):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            self.clients -= dead


# Module-level singleton — imported by main.py and skills
proactive_tts = ProactiveTTS()
