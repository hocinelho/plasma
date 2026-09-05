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


# The phrase each pre-trained openWakeWord model actually answers to. None of
# them is "Hey Plasma": that one has to be trained (scripts/train_hey_plasma.py,
# which needs TensorFlow), and until it is, saying "Hey Plasma" does nothing at
# all — she is listening for a different phrase entirely.
_PRETRAINED_PHRASES = {
    "hey_jarvis": "Hey Jarvis",
    "alexa": "Alexa",
    "hey_mycroft": "Hey Mycroft",
    "hey_rhasspy": "Hey Rhasspy",
}


def _announce_the_wake_phrase(wake_ok: bool, clap_ok: bool) -> None:
    """Say out loud what she is actually listening for.

    The fallback to a pre-trained model was already logged — as one WARNING,
    two hundred lines above the point where anyone looks, in a startup that
    prints every trigger of all 49 skills. So the single most important fact
    about talking to her hands-free was, in practice, invisible: you say "Hey
    Plasma", nothing happens, and nothing anywhere says why.

    Everything else about her can be discovered by trying it. This cannot.
    """
    if not wake_ok and not clap_ok:
        print("\n  Hands-free is OFF — tap her to talk, or set "
              "WAKE_WORD_ENABLED=true in .env.\n")
        return

    lines = []
    if wake_ok:
        model = (config.WAKE_WORD_MODEL or "").strip()
        phrase = _PRETRAINED_PHRASES.get(model)
        if phrase:
            lines.append(f'  SAY "{phrase.upper()}" to wake her — not "Hey Plasma".')
            lines.append(f"     (that is the pre-trained '{model}' model; a real")
            lines.append("      'Hey Plasma' needs: python scripts/train_hey_plasma.py)")
        else:
            # A custom model actually loaded — its name is the phrase.
            lines.append(f"  Wake word: '{model}'")
    if clap_ok:
        lines.append("  Or clap twice.")

    print("\n" + "\n".join(lines) + "\n")


def _hands_free_suppressed() -> bool:
    """True while a meeting recording is running.

    Wake word and clap are *hands-free* triggers: they fire on whatever the
    room happens to say. During a meeting that is exactly wrong, so they are
    muted until the meeting ends. Deliberate push-to-talk is unaffected.
    """
    try:
        from backend.modules.meeting.recorder import recorder as _meeting
        return _meeting.is_recording
    except Exception:
        return False


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
        _announce_the_wake_phrase(wake_ok, clap_ok)

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
                    trigger_frames=getattr(config, "WAKE_WORD_TRIGGER_FRAMES", 2),
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
                min_crest=config.CLAP_MIN_CREST,
                min_peak=config.CLAP_MIN_PEAK,
            )
            log.info(
                "Clap-to-wake active (threshold=%.1f, window=%dms, min_crest=%.1f, min_peak=%d)",
                config.CLAP_THRESHOLD, config.CLAP_WINDOW_MS, config.CLAP_MIN_CREST, config.CLAP_MIN_PEAK,
            )

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

                # While a meeting is being recorded, hands-free triggers are
                # suppressed. Meeting speech (and Plasma's own replies coming
                # back through the mic) otherwise fire the wake word and clap
                # detector constantly, so she talks over the meeting and the
                # room's words get sent to the LLM as if they were commands.
                # Push-to-talk still works — that is how you stop the meeting.
                if _hands_free_suppressed():
                    continue

                if detector:
                    result = detector.process(chunk)
                    if result["detected"]:
                        log.info("Wake word '%s' detected! score=%.2f", detector.wake_word, result["score"])
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
