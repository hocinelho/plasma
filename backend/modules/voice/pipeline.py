"""
Plasma voice pipeline — turns raw audio bytes into a transcript.

Accepts:
- int16 numpy array at 16 kHz (from the Python mic capture / hotkey path)
- OR raw bytes from a browser upload (WebM/Opus, WAV, MP3, ogg — decoded via FFmpeg)

Returns: {"text": str, "language": str, "duration": float, "latency": float}
or      {"text": "", "error": "..."} on failure.

Uses imageio-ffmpeg which ships a bundled FFmpeg binary — no system install needed.
"""
from __future__ import annotations
import io
import logging
import subprocess
from typing import Optional

import numpy as np

from backend.modules.voice.asr import WhisperASR

log = logging.getLogger("plasma.pipeline")

TARGET_SR = 16_000  # Whisper requires 16 kHz

_asr: Optional[WhisperASR] = None
_ffmpeg_path: Optional[str] = None


def get_asr() -> WhisperASR:
    """Singleton: load Whisper once, reuse across requests."""
    global _asr
    if _asr is None:
        _asr = WhisperASR()
    return _asr


def _get_ffmpeg() -> str:
    """Return the path to the bundled FFmpeg binary."""
    global _ffmpeg_path
    if _ffmpeg_path is None:
        import imageio_ffmpeg
        _ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        log.info(f"Using FFmpeg at: {_ffmpeg_path}")
    return _ffmpeg_path


def _decode_with_ffmpeg(data: bytes) -> np.ndarray:
    """
    Decode any audio bytes -> int16 mono 16 kHz numpy array via FFmpeg.

    Pipes the raw bytes on stdin, asks FFmpeg to output raw PCM on stdout.
    Works for WebM/Opus, WAV, MP3, ogg, m4a, anything FFmpeg supports.
    """
    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",          # read from stdin
        "-f", "s16le",           # output raw 16-bit little-endian PCM
        "-ac", "1",              # 1 channel (mono)
        "-ar", str(TARGET_SR),   # 16 kHz sample rate
        "pipe:1",                # write to stdout
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=data,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg decode failed: {stderr}") from e
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg decode timed out")

    audio = np.frombuffer(proc.stdout, dtype=np.int16)
    return audio


def transcribe_audio_bytes(data: bytes) -> dict:
    """Decode any common audio format and transcribe it with Whisper."""
    if not data:
        return {"text": "", "error": "empty_audio"}

    try:
        audio = _decode_with_ffmpeg(data)
    except Exception as e:
        log.error(f"Audio decode failed: {e}")
        return {"text": "", "error": f"decode_failed: {e}"}

    if len(audio) < 1600:  # < 0.1 s
        return {"text": "", "error": "audio_too_short"}

    return transcribe_array(audio)


def transcribe_array(audio: np.ndarray) -> dict:
    """Transcribe a ready-to-use int16 mono 16 kHz numpy array."""
    if audio is None or len(audio) < 1600:
        return {"text": "", "error": "audio_too_short"}

    asr = get_asr()
    result = asr.transcribe(audio)
    log.info(
        f"Transcribed: text='{result['text'][:80]}' "
        f"dur={result['duration']:.1f}s lat={result['latency']:.1f}s"
    )
    return result