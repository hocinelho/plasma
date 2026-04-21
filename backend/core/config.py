"""
Plasma configuration — loads from .env at startup.

No secrets get hard-coded. Everything read from environment / .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Locate project root (plasma/) and load .env from it
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # --- Local LLM (Ollama) ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "orca-mini:latest")

    # --- Paths ---
    PLASMA_DIR: Path = PROJECT_ROOT / ".plasma"
    MEMORY_DB: Path = PLASMA_DIR / "memory.sqlite"

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("PLASMA_LOG_LEVEL", "INFO")

    @classmethod
    def summary(cls) -> dict:
        """Non-sensitive config snapshot for /health."""
        return {
            "ollama_base_url": cls.OLLAMA_BASE_URL,
            "ollama_model": cls.OLLAMA_MODEL,
            "log_level": cls.LOG_LEVEL,
        }


config = Config()