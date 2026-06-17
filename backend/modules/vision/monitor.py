"""
Vision presence monitor — background camera loop that fires ProactiveTTS alerts.

Usage (via the vision skill):
    vision_monitor.start_watching(session_id, language, watch_for=["person"])
    vision_monitor.stop_watching()

Architecture mirrors WakeMonitor: daemon thread → detect at ~1 FPS → ProactiveTTS.fire().
Cool-down prevents re-alerting for the same object class within alert_cooldown_s seconds.
"""
from __future__ import annotations
import logging
import threading
import time

from backend.modules.vision.detector import get_detector
from backend.modules.vision.capture import LocalCameraCapture
from backend.modules.voice.proactive_tts import proactive_tts

log = logging.getLogger("plasma.vision.monitor")


class VisionMonitor:
    """Singleton background camera monitor."""

    def __init__(self) -> None:
        self.enabled = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Per-run config
        self._session_id: str = "default"
        self._language: str = "en"
        self._watch_for: set[str] = {"person"}
        self._alert_cooldown_s: float = 30.0
        self._fps: float = 1.0  # polling rate (keep low for CPU headroom)

    # ── public API ────────────────────────────────────────────────────────

    def start_watching(
        self,
        session_id: str,
        language: str,
        watch_for: list[str],
        alert_cooldown_s: float = 30.0,
        fps: float = 1.0,
    ) -> None:
        with self._lock:
            self._stop_watching_locked()  # stop any previous run
            self._session_id = session_id
            self._language = language
            self._watch_for = {w.lower() for w in watch_for}
            self._alert_cooldown_s = alert_cooldown_s
            self._fps = max(0.1, min(fps, 5.0))
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="plasma-vision-monitor",
            )
            self._thread.start()
            self.enabled = True
            log.info("VisionMonitor started: watch_for=%s fps=%.1f", self._watch_for, self._fps)

    def stop_watching(self) -> None:
        with self._lock:
            self._stop_watching_locked()

    def _stop_watching_locked(self) -> None:
        self._stop_event.set()
        self.enabled = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        log.info("VisionMonitor stopped")

    # ── internals ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        from backend.core.config import config

        detector = get_detector()
        last_seen: dict[str, float] = {}
        interval = 1.0 / self._fps

        try:
            cam = LocalCameraCapture(config.CAMERA_DEVICE)
            cam.open()
        except Exception as e:
            log.warning("VisionMonitor: camera open failed: %s", e)
            return

        log.info("VisionMonitor camera open, polling every %.1fs", interval)
        try:
            while not self._stop_event.is_set():
                t0 = time.monotonic()
                try:
                    frame = cam.capture_frame()
                    if frame is None:
                        time.sleep(interval)
                        continue

                    detections = detector.detect(frame)
                    now = time.time()

                    for d in detections:
                        label = d["label"].lower()
                        if label not in self._watch_for:
                            continue
                        since = now - last_seen.get(label, 0)
                        if since < self._alert_cooldown_s:
                            continue
                        last_seen[label] = now
                        de = self._language == "de"
                        msg = (
                            f"{label.capitalize()} erkannt!"
                            if de
                            else f"{label.capitalize()} detected!"
                        )
                        log.info("VisionMonitor alert: %s", msg)
                        proactive_tts.fire(msg, self._language)

                except Exception as e:
                    log.warning("VisionMonitor loop error: %s", e)

                elapsed = time.monotonic() - t0
                sleep = max(0.0, interval - elapsed)
                if sleep > 0:
                    time.sleep(sleep)
        finally:
            cam.close()
            log.info("VisionMonitor camera closed")


# Module-level singleton — imported by skill and main.py
vision_monitor = VisionMonitor()
