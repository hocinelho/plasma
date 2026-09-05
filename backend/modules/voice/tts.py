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
_voice_de = None

# PA-67: runtime voice override — set by the voice_select skill.
# When set, it wins over both the default and the German voice.
_voice_override = None
_voice_override_name: str | None = None

VOICES_DIR = Path(__file__).resolve().parents[3] / "voices"


def _resolve_model(model_env: str) -> Path:
    p = Path(model_env)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[3] / p
    return p


def list_available_voices() -> list[str]:
    """All Piper .onnx voice models found in the voices/ directory."""
    if not VOICES_DIR.exists():
        return []
    return sorted(p.name for p in VOICES_DIR.glob("*.onnx"))


def set_voice_override(model_path: Path | str | None) -> str | None:
    """Switch the active TTS voice at runtime (PA-67). None resets to default.

    Returns the active override voice name, or None after a reset.
    """
    global _voice_override, _voice_override_name
    if model_path is None:
        _voice_override = None
        _voice_override_name = None
        log.info("TTS voice override cleared — back to default voice")
        return None
    from piper import PiperVoice
    p = Path(model_path)
    if not p.exists():
        raise FileNotFoundError(f"Voice model not found: {p}")
    log.info(f"Loading override Piper voice: {p.name}")
    _voice_override = PiperVoice.load(str(p))
    _voice_override_name = p.stem
    return _voice_override_name


def get_voice_override_name() -> str | None:
    return _voice_override_name


def _default_voice_path() -> Optional[Path]:
    """A voice to use when TTS_VOICE_MODEL is not configured.

    scripts/download_female_voice.py drops its .onnx into voices/, and until
    now you then had to edit .env as well before she would make a sound. That
    second step serves nothing when a voice is already sitting there, and
    skipping it looked like TTS was broken rather than unconfigured.

    English is preferred because the rest of the defaults are English; beyond
    that the choice is alphabetical so it never changes between runs.
    """
    voices = sorted(VOICES_DIR.glob("*.onnx")) if VOICES_DIR.is_dir() else []
    if not voices:
        return None
    english = [v for v in voices if v.name.startswith("en")]
    return (english or voices)[0]


def _load_voice():
    global _voice
    if _voice is not None:
        return _voice
    # Work out which file before importing piper: "you have no voice yet" is
    # both the likelier problem and the more actionable message, and importing
    # first would bury it under a ModuleNotFoundError.
    if config.TTS_VOICE_MODEL:
        model_path = _resolve_model(config.TTS_VOICE_MODEL)
    else:
        found = _default_voice_path()
        if found is None:
            raise RuntimeError(
                "No TTS voice available. Run: "
                "python scripts/download_female_voice.py kristin"
            )
        log.info("TTS_VOICE_MODEL not set — using %s from voices/", found.name)
        model_path = found
    if not model_path.exists():
        raise FileNotFoundError(f"Piper voice model not found: {model_path}")
    from piper import PiperVoice
    log.info(f"Loading Piper voice: {model_path.name}")
    t0 = time.time()
    _voice = PiperVoice.load(str(model_path))
    log.info(f"Piper voice loaded in {time.time() - t0:.1f}s")
    return _voice


def _load_voice_de() -> Optional[object]:
    """Load German Piper voice if TTS_VOICE_DE is configured. Returns None if not set."""
    global _voice_de
    if _voice_de is not None:
        return _voice_de
    if not config.TTS_VOICE_DE:
        return None
    from piper import PiperVoice
    model_path = _resolve_model(config.TTS_VOICE_DE)
    if not model_path.exists():
        log.warning(f"German Piper voice not found: {model_path} — falling back to English")
        return None
    log.info(f"Loading German Piper voice: {model_path.name}")
    t0 = time.time()
    _voice_de = PiperVoice.load(str(model_path))
    log.info(f"German Piper voice loaded in {time.time() - t0:.1f}s")
    return _voice_de


def synthesize(text: str, language: str = "en") -> bytes:
    """Synthesize the given text to a mono 16-bit PCM WAV byte string."""
    text = (text or "").strip()
    if not text:
        return b""

    # Priority: runtime override (PA-67) > language-specific voice > default
    voice = _voice_override or (_load_voice_de() if language == "de" else None) or _load_voice()

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
        # Report the voice actually in use, which is not necessarily the
        # configured one — with TTS_VOICE_MODEL unset we fall back to whatever
        # is in voices/, and naming the wrong thing here sends people editing
        # a setting that was never the problem.
        chosen = (_resolve_model(config.TTS_VOICE_MODEL) if config.TTS_VOICE_MODEL
                  else _default_voice_path())
        return {
            "enabled": True,
            "loaded": True,
            "model": chosen.name if chosen else None,
            "configured": bool(config.TTS_VOICE_MODEL),
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