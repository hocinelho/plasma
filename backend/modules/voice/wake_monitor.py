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
        self._wake_ok: bool = False  # set in start()

    # ── public API ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background thread + async broadcast loop."""
        wake_ok = config.WAKE_WORD_ENABLED
        clap_ok = config.CLAP_WAKE_ENABLED

        if not wake_ok and not clap_ok:
            log.info("Wake word and clap-wake both disabled — skipping monitor")
            return

        if wake_ok:
            try:
                from openwakeword.model import Model  # noqa: F401 — probe import
            except ImportError:
                log.warning("openwakeword not installed — wake word disabled; clap-wake still active=%s", clap_ok)
                wake_ok = False
                if not clap_ok:
                    return

        self._wake_ok = wake_ok
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
            "Wake monitor started: wake_word=%s model=%s clap=%s",
            wake_ok, config.WAKE_WORD_MODEL, clap_ok,
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
        """Runs in a daemon thread: read mic → detect (wake word + clap) → enqueue."""
        from backend.modules.voice.audio_capture import AudioCapture

        # --- wake word detector (optional) ---
        detector = None
        if self._wake_ok:
            try:
                from backend.modules.voice.wake_word import WakeWordDetector
                detector = WakeWordDetector(
                    wake_word=config.WAKE_WORD_MODEL,
                    threshold=config.WAKE_WORD_THRESHOLD,
                    model_path=config.WAKE_WORD_MODEL_PATH or None,
                )
            except Exception as e:
                log.warning("Wake word detector failed to load: %s", e)

        # --- clap detector (optional, no extra deps) ---
        clap = None
        if config.CLAP_WAKE_ENABLED:
            from backend.modules.voice.clap_detector import ClapDetector
            clap = ClapDetector(
                threshold=config.CLAP_THRESHOLD,
                max_gap_ms=config.CLAP_WINDOW_MS,
            )
            log.info("Clap-to-wake active (threshold=%.1f, window=%dms)", config.CLAP_THRESHOLD, config.CLAP_WINDOW_MS)

        if not detector and not clap:
            log.warning("No active wake detectors — thread exiting")
            return

        try:
            cap = AudioCapture()
            cap.start()
            log.info("Wake detection loop running (wake_word=%s, clap=%s)", detector is not None, clap is not None)

            while not self._stop_event.is_set():
                chunk = cap.get_chunk(timeout=0.5)
                if chunk is None:
                    continue

                if detector:
                    result = detector.process(chunk)
                    if result["detected"]:
                        log.info("Wake word '%s' detected! score=%.2f", config.WAKE_WORD_MODEL, result["score"])
                        asyncio.run_coroutine_threadsafe(
                            self._queue.put({**result, "source": "wake_word"}), loop
                        )

                if clap:
                    clap_result = clap.process(chunk)
                    if clap_result["detected"]:
                        asyncio.run_coroutine_threadsafe(
                            self._queue.put({"detected": True, "score": clap_result["score"], "source": "clap"}),
                            loop,
                        )

            cap.stop()
        except Exception as e:
            log.error("Wake detection loop crashed: %s", e, exc_info=True)

    async def _broadcast_loop(self) -> None:
        """Async loop: drain detection queue → broadcast to all WS clients."""
        while True:
            result = await self._queue.get()
            dead: set[WebSocket] = set()
            for ws in list(self.clients):
                try:
                    await ws.send_json({
                        "type": "wake",
                        "score": result.get("score", 0.0),
                        "source": result.get("source", "wake_word"),
                    })
                except Exception:
                    dead.add(ws)
            self.clients -= dead


# Module-level singleton — imported by main.py
wake_monitor = WakeMonitor()
