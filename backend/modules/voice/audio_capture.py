"""
Plasma audio capture - sounddevice-based mic loop.

Goals:
- 16 kHz mono int16, matches Whisper / openWakeWord / Silero VAD native format
- Non-blocking: audio goes into a queue for downstream consumers (VAD, wake-word)
- Works with Windows default input device

Used by voice_loop.py in Step 5e. Tested standalone via __main__ block.
"""
from __future__ import annotations
import logging
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

log = logging.getLogger("plasma.audio")

SAMPLE_RATE = 16_000          # Hz — Whisper / openWakeWord native
CHANNELS = 1                  # mono
BLOCKSIZE = 1_280             # 80 ms at 16 kHz — common wake-word chunk


class AudioCapture:
    """Continuous audio capture into a thread-safe queue.

    Usage:
        cap = AudioCapture()
        cap.start()
        chunk = cap.get_chunk(timeout=1.0)  # np.int16 array of shape (1280,)
        cap.stop()
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        blocksize: int = BLOCKSIZE,
        device: Optional[int | str] = None,
    ):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.device = device
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._stream: sd.InputStream | None = None
        self._running = threading.Event()

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning(f"sounddevice status: {status}")
        # indata is float32 in [-1, 1]; convert to int16 for Whisper/OWW
        pcm16 = (indata[:, 0] * 32767.0).astype(np.int16)
        try:
            self._q.put_nowait(pcm16)
        except queue.Full:
            # Drop oldest to keep up with real-time
            try:
                self._q.get_nowait()
                self._q.put_nowait(pcm16)
            except queue.Empty:
                pass

    def start(self) -> None:
        if self._running.is_set():
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype="float32",
            blocksize=self.blocksize,
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        self._running.set()
        log.info(
            f"AudioCapture started: {self.sample_rate} Hz, blocksize={self.blocksize}, "
            f"device={self.device or 'default'}"
        )

    def stop(self) -> None:
        if not self._running.is_set():
            return
        self._running.clear()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        log.info("AudioCapture stopped")

    def get_chunk(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Return the next int16 chunk or None on timeout."""
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear(self) -> None:
        """Drop any buffered audio (use after wake-word to start fresh)."""
        with self._q.mutex:
            self._q.queue.clear()


def list_devices() -> str:
    """Return a formatted string of available audio devices."""
    return str(sd.query_devices())


if __name__ == "__main__":
    # Smoke test: record 3 seconds and report peak level
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("Available audio devices:")
    print(list_devices())
    print()

    cap = AudioCapture()
    cap.start()
    print("Recording 3 seconds — SPEAK INTO YOUR MIC NOW...")
    samples = []
    start = time.time()
    while time.time() - start < 3.0:
        chunk = cap.get_chunk(timeout=0.5)
        if chunk is not None:
            samples.append(chunk)
    cap.stop()

    if not samples:
        print("ERROR: no audio captured — check microphone permissions")
    else:
        full = np.concatenate(samples)
        peak = int(np.abs(full).max())
        rms = float(np.sqrt(np.mean(full.astype(np.float32) ** 2)))
        print(f"Captured {len(full)} samples ({len(full)/SAMPLE_RATE:.2f} s)")
        print(f"Peak level: {peak} / 32767  ({peak/32767*100:.1f}%)")
        print(f"RMS level:  {rms:.0f}")
        if peak < 500:
            print("WARNING: very quiet — speak louder or check mic selection")
        else:
            print("OK: mic is working")