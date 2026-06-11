"""
Plasma configuration — loads from .env at startup.

No secrets get hard-coded. Everything reads from environment / .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Use the OS certificate store for TLS so corporate MITM proxies (whose CA is
# trusted by Windows but absent from certifi's bundle) don't break outbound
# HTTPS. This is why some hosts (e.g. Wikipedia) hit
# "CERTIFICATE_VERIFY_FAILED" while others (Google) work. Safe no-op if the
# package isn't installed — falls back to certifi.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # --- Cloud LLM (OpenAI-compatible, provider-agnostic) ---
    # Default: Google Gemini (free tier, 1500 req/day).
    # Swap to Cerebras, OpenRouter, or Groq by changing these three vars.
    CLOUD_API_KEY: str = os.getenv("CLOUD_API_KEY", "")
    CLOUD_MODEL: str = os.getenv("CLOUD_MODEL", "gemini-2.0-flash")
    CLOUD_BASE_URL: str = os.getenv(
        "CLOUD_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    # --- Local LLM (Ollama) ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "orca-mini:latest")

    # --- Local ASR (Whisper) ---
    # tiny.en ~1s | base.en ~2s | small.en ~3-5s | medium.en ~8s (best for accents)
    # For German: use 'small' (multilingual, not small.en)
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small.en")
    # "auto" = detect language per utterance | "en" = English only | "de" = German only
    WHISPER_LANGUAGE: str = os.getenv("WHISPER_LANGUAGE", "en")
    # When WHISPER_LANGUAGE=auto, restrict detection to these languages so short,
    # accented utterances aren't mis-detected (e.g. English heard as Arabic).
    WHISPER_ALLOWED_LANGS: str = os.getenv("WHISPER_ALLOWED_LANGS", "en,de")

    # --- Wake word (PA-34) ---
    # Set WAKE_WORD_ENABLED=true in .env to enable hands-free "hey jarvis" detection.
    # Requires openwakeword (already in requirements.txt).
    WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "false").lower() == "true"
    WAKE_WORD_MODEL: str = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
    WAKE_WORD_THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

    # --- Local TTS (Piper) ---
    TTS_VOICE_MODEL: str = os.getenv("TTS_VOICE_MODEL", "")
    TTS_VOICE_DE: str = os.getenv("TTS_VOICE_DE", "")   # German voice model path
    TTS_ENABLED: bool = os.getenv("TTS_ENABLED", "true").lower() == "true"

    # --- Speaker identification (PA-65, S11) ---
    # Requires `pip install resemblyzer` (voice embedding model, ~17MB + torch).
    # Gracefully disabled if the package is missing.
    SPEAKER_ID_ENABLED: bool = os.getenv("SPEAKER_ID_ENABLED", "true").lower() == "true"
    # Cosine similarity threshold for a positive match (0.5 loose – 0.9 strict)
    SPEAKER_THRESHOLD: float = float(os.getenv("SPEAKER_THRESHOLD", "0.70"))

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("PLASMA_LOG_LEVEL", "INFO")

    # --- Spotify (PA-74/77) ---
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:9090")

    # --- Google Calendar + Gmail (alternative to Microsoft Graph) ---
    # Create a project at console.cloud.google.com, then run: python scripts/google_auth.py
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # --- Microsoft Graph (Outlook calendar + email) ---
    # Register an app at portal.azure.com, then run: python scripts/ms_auth.py
    MS_CLIENT_ID: str = os.getenv("MS_CLIENT_ID", "")
    MS_TENANT_ID: str = os.getenv("MS_TENANT_ID", "common")  # "common" = personal + work

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