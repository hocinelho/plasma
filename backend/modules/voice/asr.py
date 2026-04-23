"""
Plasma automatic speech recognition - faster-whisper wrapper.

Uses OpenAI Whisper via CTranslate2 for CPU-friendly inference.
Default model: 'small.en' — English-only, ~500 MB, good CPU speed.

Input:  int16 mono numpy array at 16 kHz (from AudioCapture buffer)
Output: transcribed text string
"""
from __future__ import annotations
import logging
import sys
import time
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

log = logging.getLogger("plasma.asr")

DEFAULT_MODEL = "small.en"
DEFAULT_SAMPLE_RATE = 16_000


class WhisperASR:
    """Wrapper around faster-whisper.

    Loads once, reuse the same instance across many transcriptions.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_name = model_name
        log.info(f"Loading faster-whisper model '{model_name}' ({compute_type} on {device})...")
        t0 = time.time()
        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
        log.info(f"Whisper loaded in {time.time() - t0:.1f}s")

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        language: Optional[str] = "en",
        beam_size: int = 5,
    ) -> dict:
        """Transcribe a numpy audio array and return text + metadata.

        Args:
            audio: int16 mono samples at `sample_rate`
            sample_rate: must be 16000 for Whisper; we assert
            language: "en", "de", etc. or None for auto-detect
            beam_size: higher = more accurate but slower

        Returns:
            {"text": str, "language": str, "duration": float, "latency": float}
        """
        assert sample_rate == DEFAULT_SAMPLE_RATE, (
            f"Whisper expects 16 kHz, got {sample_rate}"
        )

        # Whisper wants float32 in [-1, 1]
        float_audio = (audio.astype(np.float32) / 32768.0).copy()

        t0 = time.time()
        segments, info = self.model.transcribe(
            float_audio,
            language=language,
            beam_size=beam_size,
            vad_filter=False,   # we already did VAD upstream
            condition_on_previous_text=False,
        )
        parts = [seg.text for seg in segments]
        text = "".join(parts).strip()
        latency = time.time() - t0

        return {
            "text": text,
            "language": info.language,
            "duration": float(info.duration),
            "latency": latency,
        }


def _smoke_test() -> None:
    """Record 5 seconds of mic audio, transcribe it."""
    from backend.modules.voice.audio_capture import AudioCapture

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    print("Loading Whisper (first run downloads ~500 MB)...", flush=True)
    asr = WhisperASR()

    print("Starting mic...", flush=True)
    cap = AudioCapture()
    cap.start()

    print("\n*** SPEAK A SENTENCE NOW (5 seconds) ***", flush=True)
    samples = []
    start = time.time()
    while time.time() - start < 5.0:
        chunk = cap.get_chunk(timeout=0.5)
        if chunk is not None:
            samples.append(chunk)
    cap.stop()

    audio = np.concatenate(samples)
    print(f"\nCaptured {len(audio)/16000:.2f}s of audio, transcribing...", flush=True)

    result = asr.transcribe(audio)
    print("\n=== TRANSCRIPTION ===", flush=True)
    print(f"Text:     \"{result['text']}\"", flush=True)
    print(f"Language: {result['language']}", flush=True)
    print(f"Duration: {result['duration']:.2f}s  (audio length)", flush=True)
    print(f"Latency:  {result['latency']:.2f}s  (processing time)", flush=True)
    speed = result['duration'] / max(result['latency'], 0.01)
    print(f"Speed:    {speed:.1f}x real-time", flush=True)


if __name__ == "__main__":
    _smoke_test()