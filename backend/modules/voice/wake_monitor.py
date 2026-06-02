"""
PA-34 — Wake word monitor service.

Runs WakeWordDetector in a daemon thread, bridges detections to the
async FastAPI world via asyncio.Queue, then broadcasts to all connected
WebSocket clients.

Wake word is optional: if WAKE_WORD_ENABLED=false (the default) the
monitor is a no-op and the app works exactly as before (push-to-talk).
"""
from __future__ import annotations
import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

from backend.core.config import config

log = logging.getLogger("plasma.wake_monitor")


class WakeMonitor:
    """Singleton service: mic → WakeWordDetector → WebSocket broadcast."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue | None = None
        self._broadcast_task: asyncio.Task | None = None

    # ── public API ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background thread + async broadcast loop."""
        if not config.WAKE_WORD_ENABLED:
            log.info("Wake word disabled (WAKE_WORD_ENABLED=false) — skipping")
            return

        try:
            from openwakeword.model import Model  # noqa: F401 — probe import
        except ImportError:
            log.warning("openwakeword not installed — wake word disabled")
            return

        self._queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._detection_loop,
            args=(loop,),
            daemon=True,
            name="plasma-wake",
        )
        self._thread.start()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        log.info(
            f"Wake monitor started: model={config.WAKE_WORD_MODEL} "
            f"threshold={config.WAKE_WORD_THRESHOLD}"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._broadcast_task:
            self._broadcast_task.cancel()

    def add_client(self, ws: WebSocket) -> None:
        self.clients.add(ws)
        log.debug(f"Wake WS client added (total={len(self.clients)})")

    def remove_client(self, ws: WebSocket) -> None:
        self.clients.discard(ws)
        log.debug(f"Wake WS client removed (total={len(self.clients)})")

    # ── internals ─────────────────────────────────────────────────────────

    def _detection_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Runs in a daemon thread: read mic → detect → enqueue."""
        from backend.modules.voice.audio_capture import AudioCapture
        from backend.modules.voice.wake_word import WakeWordDetector

        try:
            detector = WakeWordDetector(
                wake_word=config.WAKE_WORD_MODEL,
                threshold=config.WAKE_WORD_THRESHOLD,
            )
            cap = AudioCapture()
            cap.start()
            log.info("Wake word detection loop running")

            while not self._stop_event.is_set():
                chunk = cap.get_chunk(timeout=0.5)
                if chunk is None:
                    continue
                result = detector.process(chunk)
                if result["detected"]:
                    log.info(f"Wake word '{config.WAKE_WORD_MODEL}' detected! score={result['score']:.2f}")
                    asyncio.run_coroutine_threadsafe(
                        self._queue.put(result), loop
                    )

            cap.stop()
        except Exception as e:
            log.error(f"Wake detection loop crashed: {e}", exc_info=True)

    async def _broadcast_loop(self) -> None:
        """Async loop: drain detection queue → broadcast to all WS clients."""
        while True:
            result = await self._queue.get()
            dead: set[WebSocket] = set()
            for ws in list(self.clients):
                try:
                    await ws.send_json({"type": "wake", "score": result["score"]})
                except Exception:
                    dead.add(ws)
            self.clients -= dead


# Module-level singleton — imported by main.py
wake_monitor = WakeMonitor()
