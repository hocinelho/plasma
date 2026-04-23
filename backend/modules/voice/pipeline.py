"""
Plasma voice pipeline — turns raw audio bytes into a transcript.

Accepts:
- int16 numpy array at 16 kHz (from the Python mic capture / hotkey path)
- OR raw bytes from a browser upload (WebM, WAV, ogg — decoded via soundfile)

Returns: transcript string.

VAD is NOT run here — we trust that the caller already ensured the audio
contains speech (push-to-talk users press a key, so the full clip is speech).
"""
from __future__ import annotations
import io
import logging
from typing import Optional

import numpy as np
import soundfile as sf

from backend.modules.voice.asr import WhisperASR

log = logging.getLogger("plasma.pipeline")

_asr: Optional[WhisperASR] = None


def get_asr() -> WhisperASR:
    """Singleton: load Whisper once, reuse across requests."""
    global _asr
    if _asr is None:
        _asr = WhisperASR()
    return _asr


def transcribe_audio_bytes(data: bytes) -> dict:
    """
    Decode any common audio format (webm, wav, ogg) and transcribe.

    Uses soundfile, which handles WAV/FLAC natively and WebM via libsndfile's
    system defaults on Windows (via the underlying libsndfile 1.2+).
    """
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="int16")
    except Exception as e:
        log.error(f"Failed to decode audio: {e}")
        return {"text": "", "error": f"decode_failed: {e}"}

    # Downmix to mono if needed
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.int16)

    # Resample to 16 kHz if needed (Whisper requires it)
    if sr != 16_000:
        audio = _resample_int16(audio, sr, 16_000)
        sr = 16_000

    return transcribe_array(audio)


def transcribe_array(audio: np.ndarray) -> dict:
    """Transcribe an int16 mono 16kHz numpy array."""
    if audio is None or len(audio) < 1600:  # less than 0.1s
        return {"text": "", "error": "audio_too_short"}

    asr = get_asr()
    result = asr.transcribe(audio)
    log.info(
        f"Transcribed: text='{result['text'][:80]}' "
        f"dur={result['duration']:.1f}s lat={result['latency']:.1f}s"
    )
    return result


def _resample_int16(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Simple linear resampler for int16 audio. Good enough for speech."""
    if src_sr == dst_sr:
        return audio
    duration = len(audio) / src_sr
    new_len = int(duration * dst_sr)
    x_old = np.linspace(0, 1, num=len(audio), endpoint=False)
    x_new = np.linspace(0, 1, num=new_len, endpoint=False)
    resampled = np.interp(x_new, x_old, audio.astype(np.float32))
    return resampled.astype(np.int16)