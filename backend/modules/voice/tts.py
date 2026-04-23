"""
Plasma text-to-speech — Piper wrapper.

Piper is a fast, local neural TTS. We load the voice model once and reuse it
for every synthesis request. Output is 16-bit PCM WAV bytes, ready to send to
the browser for playback.

Piper 1.4+ API: voice.synthesize() returns an iterator of AudioChunk objects.
We collect them and wrap the PCM in a WAV container.
"""
from __future__ import annotations
import io
import logging
import time
import wave
from pathlib import Path
from typing import Optional

from backend.core.config import config

log = logging.getLogger("plasma.tts")

_voice = None


def _load_voice():
    """Load the Piper voice model once; cache the instance."""
    global _voice
    if _voice is not None:
        return _voice

    if not config.TTS_VOICE_MODEL:
        raise RuntimeError("TTS_VOICE_MODEL not set in .env")

    from piper import PiperVoice

    model_path = Path(config.TTS_VOICE_MODEL)
    if not model_path.is_absolute():
        project_root = Path(__file__).resolve().parents[3]
        model_path = project_root / model_path

    if not model_path.exists():
        raise FileNotFoundError(f"Piper voice model not found: {model_path}")

    log.info(f"Loading Piper voice: {model_path.name}")
    t0 = time.time()
    _voice = PiperVoice.load(str(model_path))
    log.info(f"Piper voice loaded in {time.time() - t0:.1f}s")
    return _voice


def synthesize(text: str) -> bytes:
    """Synthesize the given text to a mono 16-bit PCM WAV byte string."""
    text = (text or "").strip()
    if not text:
        return b""

    voice = _load_voice()

    t0 = time.time()

    # Collect all PCM frames from Piper's AudioChunk iterator
    pcm_parts: list[bytes] = []
    sample_rate = 22050  # Piper default; we override from the first chunk
    for chunk in voice.synthesize(text):
        # Newer Piper: chunk is an AudioChunk with audio_int16_bytes + sample_rate attrs
        if hasattr(chunk, "audio_int16_bytes"):
            pcm_parts.append(chunk.audio_int16_bytes)
            sample_rate = chunk.sample_rate
        # Older Piper: chunk might already be raw bytes
        elif isinstance(chunk, (bytes, bytearray)):
            pcm_parts.append(bytes(chunk))

    pcm = b"".join(pcm_parts)

    # Wrap the raw PCM in a WAV container
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)

    wav_bytes = buf.getvalue()
    log.info(
        f"TTS synth: {len(text)} chars -> {len(wav_bytes)} bytes "
        f"({(time.time() - t0):.2f}s, sr={sample_rate})"
    )
    return wav_bytes


def health_check() -> dict:
    """Probe: is TTS configured and the model reachable?"""
    if not config.TTS_ENABLED:
        return {"enabled": False, "loaded": False, "model": None}

    try:
        _load_voice()
        return {
            "enabled": True,
            "loaded": True,
            "model": Path(config.TTS_VOICE_MODEL).name,
        }
    except Exception as e:
        return {"enabled": True, "loaded": False, "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sample = "Hello, I am Plasma. Your local-first voice assistant is online."
    print(f"Synthesizing: {sample!r}")
    wav = synthesize(sample)

    out_path = Path("tts_test.wav")
    out_path.write_bytes(wav)
    print(f"Wrote {len(wav)} bytes to {out_path.resolve()}")
    print("Open tts_test.wav in any media player to hear the voice.")