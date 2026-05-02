"""
Plasma configuration — loads from .env at startup.

No secrets get hard-coded. Everything reads from environment / .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # --- Local LLM (Ollama) ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "orca-mini:latest")

    # --- Local ASR (Whisper) ---
    # tiny.en ~1s | base.en ~2s | small.en ~3-5s | medium.en ~8s (best for accents)
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small.en")

    # --- Local TTS (Piper) ---
    TTS_VOICE_MODEL: str = os.getenv("TTS_VOICE_MODEL", "")
    TTS_ENABLED: bool = os.getenv("TTS_ENABLED", "true").lower() == "true"

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("PLASMA_LOG_LEVEL", "INFO")

    # --- Paths ---
    PLASMA_DIR: Path = PROJECT_ROOT / ".plasma"
    MEMORY_DB: Path = PLASMA_DIR / "memory.sqlite"

    @classmethod
    def summary(cls) -> dict:
        return {
            "ollama_base_url": cls.OLLAMA_BASE_URL,
            "ollama_model": cls.OLLAMA_MODEL,
            "tts_enabled": cls.TTS_ENABLED,
            "tts_voice_model": cls.TTS_VOICE_MODEL,
            "log_level": cls.LOG_LEVEL,
        }


config = Config()