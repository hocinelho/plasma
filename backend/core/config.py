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
    # "openai" (default) speaks the OpenAI /chat/completions wire protocol that
    # Gemini/Cerebras/OpenRouter/Groq all share. "anthropic" switches cloud_client
    # to Claude's native Messages API (PA-32) — different endpoint/auth/response
    # shape, so it can't be reached by just pointing CLOUD_BASE_URL at Anthropic.
    CLOUD_PROVIDER: str = os.getenv("CLOUD_PROVIDER", "openai").strip().lower()

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

    # --- Wake word (PA-34 / PA-89) ---
    # Set WAKE_WORD_ENABLED=true in .env to enable hands-free detection.
    # Requires openwakeword (already in requirements.txt).
    WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "false").lower() == "true"
    # Pre-trained model name (fallback when WAKE_WORD_MODEL_PATH not set)
    WAKE_WORD_MODEL: str = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
    WAKE_WORD_THRESHOLD: float = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))
    # Path to a custom .onnx wake word model trained via scripts/train_hey_plasma.py
    # When set and file exists, used instead of WAKE_WORD_MODEL.
    WAKE_WORD_MODEL_PATH: str = os.getenv("WAKE_WORD_MODEL_PATH", "")

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

    # --- Microsoft Graph (Outlook calendar + email + Teams meetings) ---
    # Register an app at portal.azure.com, then run: python scripts/ms_auth.py
    MS_CLIENT_ID: str = os.getenv("MS_CLIENT_ID", "")
    MS_TENANT_ID: str = os.getenv("MS_TENANT_ID", "common")  # "common" = personal + work

    # --- Slack (PA-78, S13) ---
    SLACK_USER_TOKEN: str = os.getenv("SLACK_USER_TOKEN", "")

    # --- WhatsApp via Twilio (PA-80, S13) ---
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # --- Home Assistant smart home integration ---
    # Run Home Assistant locally (https://www.home-assistant.io/) or on a Pi.
    # Generate a Long-Lived Access Token: Profile → Long-Lived Access Tokens.
    HA_BASE_URL: str = os.getenv("HA_BASE_URL", "http://homeassistant.local:8123")
    HA_TOKEN: str = os.getenv("HA_TOKEN", "")
    # Default light entity controlled when no room is specified
    HA_LIGHT_ENTITY: str = os.getenv("HA_LIGHT_ENTITY", "light.all")

    # --- Clap-to-wake (double-clap detection, pure numpy, no ML model) ---
    CLAP_WAKE_ENABLED: bool = os.getenv("CLAP_WAKE_ENABLED", "false").lower() == "true"
    # How many times louder than background the clap peak must be (8 = default)
    CLAP_THRESHOLD: float = float(os.getenv("CLAP_THRESHOLD", "8.0"))
    # Max gap between the two claps in milliseconds
    CLAP_WINDOW_MS: int = int(os.getenv("CLAP_WINDOW_MS", "600"))

    # --- Camera / vision (MediaPipe, Apache 2.0) ---
    CAMERA_ENABLED: bool = os.getenv("CAMERA_ENABLED", "false").lower() == "true"
    # OpenCV device index for local webcam (0 = default camera)
    CAMERA_DEVICE: int = int(os.getenv("CAMERA_DEVICE", "0"))
    # Minimum confidence score to report a detected object (0.0–1.0)
    VISION_SCORE_THRESHOLD: float = float(os.getenv("VISION_SCORE_THRESHOLD", "0.5"))
    # Where to cache the MediaPipe EfficientDet model (~4.4 MB, auto-downloaded)
    VISION_MODEL_DIR: Path = Path(os.getenv(
        "VISION_MODEL_DIR",
        str(Path(__file__).resolve().parents[2] / ".plasma" / "models"),
    ))

    # --- LocateAnything open-vocabulary detection — 3-tier backend ---
    # Tier 1 (fastest, zero install): cloud vision LLM — uses CLOUD_API_KEY above.
    #   Uses CLOUD_MODEL by default. Override with LOCATE_CLOUD_MODEL to pick a
    #   vision-capable model without changing your main chat model.
    #   On OpenRouter, free vision model: google/gemini-2.0-flash-exp:free
    LOCATE_CLOUD_MODEL: str = os.getenv("LOCATE_CLOUD_MODEL", "")
    # Tier 2 (offline, fast): Ollama vision model (moondream ~1.9 GB).
    #   Enable: ollama pull moondream  then set:
    LOCATE_VISION_OLLAMA_MODEL: str = os.getenv("LOCATE_VISION_OLLAMA_MODEL", "")
    # Tier 3 (offline, heavy): locate-anything.cpp CLI (6 GB GGUF, C++ build).
    #   See external/locate-anything/README.md for build instructions.
    LOCATE_ANYTHING_BIN: str = os.getenv("LOCATE_ANYTHING_BIN", "")
    LOCATE_ANYTHING_MODEL: str = os.getenv("LOCATE_ANYTHING_MODEL", "")
    # hybrid (default) | slow | fast
    LOCATE_ANYTHING_MODE: str = os.getenv("LOCATE_ANYTHING_MODE", "hybrid")
    # CPU threads for the CLI. 0 = let the binary decide. On a many-core machine
    # set this to (cores - 2) so inference is fast but the PC stays responsive.
    LOCATE_ANYTHING_THREADS: int = int(os.getenv("LOCATE_ANYTHING_THREADS", "0"))
    # Seconds to allow the (slow, CPU) inference before giving up
    LOCATE_ANYTHING_TIMEOUT: float = float(os.getenv("LOCATE_ANYTHING_TIMEOUT", "60"))
    # Remote server URL — if set, the CLI subprocess is skipped entirely and the
    # image is POSTed to this server. Takes priority over local BIN/MODEL.
    LOCATE_ANYTHING_SERVER_URL: str = os.getenv("LOCATE_ANYTHING_SERVER_URL", "")

    # --- Image generation via Muapi.ai (Open-Generative-AI backend) ---
    # Get a key at https://muapi.ai. "generate an image of X" → image URL.
    MUAPI_API_KEY: str = os.getenv("MUAPI_API_KEY", "")
    MUAPI_BASE_URL: str = os.getenv("MUAPI_BASE_URL", "https://api.muapi.ai")
    # Model endpoint slug (POST /api/v1/<endpoint>). Default: a fast Flux model.
    # NOTE: MUAPI text-to-image slugs end in "-image" (e.g. flux-schnell-image,
    # flux-dev-image). A bare "flux-schnell" returns 404.
    MUAPI_IMAGE_MODEL: str = os.getenv("MUAPI_IMAGE_MODEL", "flux-schnell-image")
    # Max seconds to poll for the generated image before giving up
    MUAPI_TIMEOUT: float = float(os.getenv("MUAPI_TIMEOUT", "120"))

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