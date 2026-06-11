"""
Plasma wake-word detection — openWakeWord wrapper.

Supports two modes:
  1. Pre-trained model by name (e.g. "hey_jarvis") — works out of the box
  2. Custom .onnx model by file path (e.g. ".plasma/models/hey_plasma.onnx")
     — trained via scripts/train_hey_plasma.py

Input: int16 chunks at 16 kHz, 1280 samples (80 ms) per chunk.
Output: {"detected": bool, "score": float}
"""
from __future__ import annotations
import logging
import sys
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("plasma.wake")

try:
    from openwakeword.model import Model
except ImportError:
    Model = None  # type: ignore  — gracefully absent; WakeWordDetector raises on use

OWW_SAMPLE_RATE = 16_000
OWW_FRAME = 1_280  # 80 ms at 16 kHz — expected frame size


class WakeWordDetector:
    """Always-on detector that returns True when the wake word is spoken.

    Pass model_path to use a custom .onnx file (e.g. "hey_plasma.onnx"
    trained via scripts/train_hey_plasma.py).  If model_path is given but
    the file doesn't exist yet, falls back to the named wake_word model.

    Usage:
        wake = WakeWordDetector(model_path=".plasma/models/hey_plasma.onnx")
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
        model_path: Optional[str] = None,
    ):
        self.threshold = threshold
        self.cooldown_samples = cooldown_ms * OWW_SAMPLE_RATE // 1000
        self._cooldown_remaining = 0
        self._buffer: deque[int] = deque()

        if Model is None:
            raise ImportError(
                "openwakeword is not installed. "
                "Run: pip install openwakeword"
            )

        if model_path and Path(model_path).exists():
            # Custom model loaded from file — score dict key is the stem name
            self.wake_word = Path(model_path).stem
            log.info(
                f"Loading custom wake word model '{model_path}' "
                f"(key='{self.wake_word}', threshold={threshold})"
            )
            self.model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx",
            )
        elif model_path and not Path(model_path).exists():
            log.warning(
                f"Custom model '{model_path}' not found — "
                f"falling back to pre-trained '{wake_word}'. "
                f"Run: python scripts/train_hey_plasma.py"
            )
            self.wake_word = wake_word
            self.model = Model(
                wakeword_models=[wake_word],
                inference_framework="onnx",
            )
        else:
            self.wake_word = wake_word
            log.info(
                f"Loading pre-trained openWakeWord model '{wake_word}' "
                f"(threshold={threshold})"
            )
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
    from backend.core.config import config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    model_path = config.WAKE_WORD_MODEL_PATH or None
    model_name = config.WAKE_WORD_MODEL

    print("Loading wake-word detector...", flush=True)
    wake = WakeWordDetector(
        wake_word=model_name,
        threshold=config.WAKE_WORD_THRESHOLD,
        model_path=model_path,
    )

    label = wake.wake_word.replace("_", " ").title()
    print(f"Starting mic... wake word: '{label}'", flush=True)
    cap = AudioCapture()
    cap.start()

    print(f"\n*** Say '{label}' several times over the next 30 seconds ***\n", flush=True)

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

        if elapsed - last_score_log > 2.0:
            print(
                f"[{elapsed:5.2f}s]  tick  last_score={result['score']:.2f}  max_so_far={max_score:.2f}",
                flush=True,
            )
            last_score_log = elapsed

    cap.stop()
    print(f"\nDone. Total detections: {detections}. Max score: {max_score:.2f}", flush=True)


if __name__ == "__main__":
    _smoke_test()
