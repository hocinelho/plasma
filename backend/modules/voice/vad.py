"""
Plasma voice activity detection — Silero VAD wrapper (official pip package).

Uses the `silero-vad` pip package which wraps the official Silero V5 model
via torch. Simpler and more reliable than calling ONNX directly.

Input: 16 kHz mono int16 chunks (from AudioCapture).
Output: speech_start / speech_end events with hysteresis.
"""
from __future__ import annotations
import logging
import sys
from collections import deque
from typing import Optional

import numpy as np
import torch
from silero_vad import load_silero_vad

log = logging.getLogger("plasma.vad")

SILERO_SAMPLE_RATE = 16_000
SILERO_WINDOW = 512  # samples Silero V5 expects per inference (32 ms)


class SileroVAD:
    """Wraps Silero VAD V5 with speech-start / speech-end detection.

    Call `process(chunk)` with each int16 chunk from AudioCapture.
    Returns {"event": None|"speech_start"|"speech_end", "prob": float, "in_speech": bool}
    """

    def __init__(
        self,
        speech_threshold: float = 0.5,
        silence_ms: int = 500,
        min_speech_ms: int = 250,
    ):
        self.speech_threshold = speech_threshold
        self.silence_samples = silence_ms * SILERO_SAMPLE_RATE // 1000
        self.min_speech_samples = min_speech_ms * SILERO_SAMPLE_RATE // 1000

        log.info("Loading Silero VAD v5 via pip package...")
        self.model = load_silero_vad()
        self.model.eval()
        log.info("Silero VAD loaded")

        self._buffer: deque[int] = deque()
        self._in_speech = False
        self._silence_run = 0
        self._speech_run = 0

    def _infer(self, window: np.ndarray) -> float:
        """Return speech probability for a 512-sample int16 window."""
        x = torch.from_numpy(window.astype(np.float32) / 32768.0)
        with torch.no_grad():
            prob = self.model(x, SILERO_SAMPLE_RATE).item()
        return float(prob)

    def process(self, chunk: np.ndarray) -> dict:
        self._buffer.extend(chunk.tolist())

        event = None
        prob = 0.0

        while len(self._buffer) >= SILERO_WINDOW:
            window = np.array(
                [self._buffer.popleft() for _ in range(SILERO_WINDOW)],
                dtype=np.int16,
            )
            prob = self._infer(window)
            is_speech = prob >= self.speech_threshold

            if is_speech:
                self._silence_run = 0
                self._speech_run += SILERO_WINDOW
                if not self._in_speech and self._speech_run >= self.min_speech_samples:
                    self._in_speech = True
                    event = "speech_start"
            else:
                if self._in_speech:
                    self._silence_run += SILERO_WINDOW
                    if self._silence_run >= self.silence_samples:
                        self._in_speech = False
                        self._silence_run = 0
                        self._speech_run = 0
                        event = "speech_end"
                else:
                    self._speech_run = 0

        return {"event": event, "prob": prob, "in_speech": self._in_speech}

    def reset(self) -> None:
        self.model.reset_states()
        self._buffer.clear()
        self._in_speech = False
        self._silence_run = 0
        self._speech_run = 0


def _smoke_test() -> None:
    """Run VAD against the live microphone for 15 seconds."""
    import time
    from backend.modules.voice.audio_capture import AudioCapture

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    print("Initializing Silero VAD...", flush=True)
    vad = SileroVAD()

    print("Starting microphone...", flush=True)
    cap = AudioCapture()
    cap.start()

    print("\nSpeak into the mic.", flush=True)
    print("VAD will print speech_start / speech_end events.", flush=True)
    print("Listening for 15 seconds...\n", flush=True)

    start = time.time()
    last_prob_log = 0.0
    while time.time() - start < 15.0:
        chunk = cap.get_chunk(timeout=0.5)
        if chunk is None:
            continue
        result = vad.process(chunk)
        elapsed = time.time() - start

        # Print events immediately
        if result["event"]:
            print(f"[{elapsed:5.2f}s] {result['event']:13s}  prob={result['prob']:.2f}", flush=True)

        # Also print a periodic probability ping so we see the script is alive
        if elapsed - last_prob_log > 1.0:
            print(f"[{elapsed:5.2f}s] tick  prob={result['prob']:.2f}  in_speech={result['in_speech']}", flush=True)
            last_prob_log = elapsed

    cap.stop()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    _smoke_test()