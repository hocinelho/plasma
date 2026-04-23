"""
Plasma wake-word detection — openWakeWord wrapper.

Default wake word: "hey_jarvis" (pre-trained model ships with openWakeWord).
Later we'll train a "hey_plasma" model via Colab and swap the model_name.

Input: same int16 chunks as AudioCapture (1280 samples / 80 ms).
Output: dict with "detected" (bool) and "score" (0..1).

Note on tuning: openWakeWord's pre-trained models are *conservative* by design.
For "hey_jarvis" a threshold of 0.3 is the documented sweet spot; 0.5 will miss
most natural speech. We keep an internal cooldown to avoid repeat triggers.
"""
from __future__ import annotations
import logging
import sys
from collections import deque
from typing import Optional

import numpy as np
from openwakeword.model import Model

log = logging.getLogger("plasma.wake")

OWW_SAMPLE_RATE = 16_000
OWW_FRAME = 1_280  # 80 ms at 16 kHz — expected frame size


class WakeWordDetector:
    """Always-on detector that returns True when the wake word is spoken.

    Usage:
        wake = WakeWordDetector(wake_word="hey_jarvis")
        for chunk in mic_chunks:
            result = wake.process(chunk)
            if result["detected"]:
                start_listening()
    """

    def __init__(
        self,
        wake_word: str = "hey_jarvis",
        threshold: float = 0.3,
        cooldown_ms: int = 1500,
    ):
        self.wake_word = wake_word
        self.threshold = threshold
        self.cooldown_samples = cooldown_ms * OWW_SAMPLE_RATE // 1000
        self._cooldown_remaining = 0
        self._buffer: deque[int] = deque()

        log.info(f"Loading openWakeWord model '{wake_word}' (threshold={threshold})...")
        self.model = Model(
            wakeword_models=[wake_word],
            inference_framework="onnx",
        )
        log.info("openWakeWord model loaded")

    def process(self, chunk: np.ndarray) -> dict:
        """Process one audio chunk; return {"detected": bool, "score": float}."""
        self._buffer.extend(chunk.tolist())

        detected = False
        top_score = 0.0

        while len(self._buffer) >= OWW_FRAME:
            frame = np.array(
                [self._buffer.popleft() for _ in range(OWW_FRAME)],
                dtype=np.int16,
            )

            # Always feed the model so its buffer stays warm,
            # but suppress detection events while in cooldown.
            scores = self.model.predict(frame)
            score = float(scores.get(self.wake_word, 0.0))
            top_score = max(top_score, score)

            if self._cooldown_remaining > 0:
                self._cooldown_remaining -= OWW_FRAME
                continue

            if score >= self.threshold:
                detected = True
                self._cooldown_remaining = self.cooldown_samples

        return {"detected": detected, "score": top_score}

    def reset(self) -> None:
        self.model.reset()
        self._buffer.clear()
        self._cooldown_remaining = 0


def _smoke_test() -> None:
    """Listen to the mic for 30 seconds, print every wake-word detection."""
    import time
    from backend.modules.voice.audio_capture import AudioCapture

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    print("Loading wake-word detector...", flush=True)
    wake = WakeWordDetector(wake_word="hey_jarvis", threshold=0.3)

    print("Starting mic...", flush=True)
    cap = AudioCapture()
    cap.start()

    print("\n*** Say 'Hey Jarvis' several times over the next 30 seconds ***", flush=True)
    print("Try with pauses between, and also in normal speech to test false positives.\n", flush=True)

    start = time.time()
    max_score = 0.0
    last_score_log = 0.0
    detections = 0
    while time.time() - start < 30.0:
        chunk = cap.get_chunk(timeout=0.5)
        if chunk is None:
            continue
        result = wake.process(chunk)
        max_score = max(max_score, result["score"])
        elapsed = time.time() - start

        if result["detected"]:
            detections += 1
            print(
                f"[{elapsed:5.2f}s]  WAKE WORD DETECTED   score={result['score']:.2f}",
                flush=True,
            )

        # Periodic score tick so we see what scores speech is generating
        if elapsed - last_score_log > 2.0:
            print(
                f"[{elapsed:5.2f}s]  tick  last_score={result['score']:.2f}  max_so_far={max_score:.2f}",
                flush=True,
            )
            last_score_log = elapsed

    cap.stop()
    print(f"\nDone. Total detections: {detections}. Max score: {max_score:.2f}", flush=True)
    if detections == 0:
        print(
            "\nZero detections. Try lowering threshold to 0.2, or check "
            "you said 'HEY Jarvis' (both words, with the 'hey').",
            flush=True,
        )
    elif max_score < 0.4:
        print(
            "\nAll scores stayed below 0.4. Speak the wake word more clearly "
            "or lower the threshold in wake_word.py.",
            flush=True,
        )


if __name__ == "__main__":
    _smoke_test()