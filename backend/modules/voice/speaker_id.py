"""
PA-65 — Speaker identification via voice embeddings.

Uses resemblyzer (GE2E speaker encoder) to turn an utterance into a 256-dim
embedding, then matches it against enrolled profiles with cosine similarity.

Design:
- resemblyzer is an OPTIONAL dependency (it pulls in torch). If it is not
  installed, is_available() returns False and identification is silently
  skipped — Plasma keeps working single-user.
- Profiles live in .plasma/speakers.json: {"name": [256 floats], ...}
- Enrollment is voice-driven: "remember my voice as Hocine" (EN) or
  "merke dir meine stimme als Hocine" (DE). main.py intercepts the phrase
  BEFORE skill routing because enrollment needs the raw audio.
- numpy is imported lazily so this module (regex parsing, profile store)
  stays importable in environments without the voice stack.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from typing import Optional

from backend.core.config import config

log = logging.getLogger("plasma.speaker_id")

PROFILES_PATH = config.PLASMA_DIR / "speakers.json"

# Utterances shorter than this carry too little voice to embed reliably
MIN_AUDIO_SECONDS = 1.0
SAMPLE_RATE = 16_000

# "remember/enroll/register/learn my voice as <name>" + German variant
_ENROLL_RE = re.compile(
    r"(?:remember|enroll|register|learn)\s+my\s+voice\s+(?:as\s+)?([a-zA-ZÀ-ÿ]+)"
    r"|merke?\s*(?:dir)?\s*meine\s+stimme\s+als\s+([a-zA-ZÀ-ÿ]+)",
    re.IGNORECASE,
)

_encoder = None
_encoder_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Enrollment phrase parsing (pure python — works without resemblyzer/numpy)
# ---------------------------------------------------------------------------
def parse_enroll_command(text: str) -> Optional[str]:
    """Return the speaker name if the utterance is an enrollment command."""
    m = _ENROLL_RE.search((text or "").strip())
    if not m:
        return None
    name = m.group(1) or m.group(2)
    return name.strip().capitalize() if name else None


# ---------------------------------------------------------------------------
# Profile store
# ---------------------------------------------------------------------------
def _load_profiles() -> dict[str, list[float]]:
    try:
        if PROFILES_PATH.exists():
            return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Could not read speaker profiles: {e}")
    return {}


def _save_profiles(profiles: dict[str, list[float]]) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(profiles), encoding="utf-8")


def list_speakers() -> list[str]:
    return sorted(_load_profiles().keys())


def forget_speaker(name: str) -> bool:
    profiles = _load_profiles()
    key = name.strip().capitalize()
    if key in profiles:
        del profiles[key]
        _save_profiles(profiles)
        return True
    return False


# ---------------------------------------------------------------------------
# Embedding backend (resemblyzer — optional)
# ---------------------------------------------------------------------------
def is_available() -> bool:
    """True if speaker ID is enabled in config AND resemblyzer is installed."""
    if not config.SPEAKER_ID_ENABLED:
        return False
    try:
        import resemblyzer  # noqa: F401
        return True
    except ImportError:
        return False


def _get_encoder():
    global _encoder
    with _encoder_lock:
        if _encoder is None:
            from resemblyzer import VoiceEncoder
            log.info("Loading resemblyzer voice encoder...")
            _encoder = VoiceEncoder("cpu")
            log.info("Voice encoder loaded")
    return _encoder


def _embed(audio_int16) -> list[float]:
    """int16 mono 16 kHz numpy array → 256-dim embedding (unit-normalized)."""
    import numpy as np
    from resemblyzer import preprocess_wav

    float_audio = audio_int16.astype(np.float32) / 32768.0
    wav = preprocess_wav(float_audio, source_sr=SAMPLE_RATE)
    emb = _get_encoder().embed_utterance(wav)
    return [float(x) for x in emb]


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-python cosine similarity (embeddings are short lists)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def enroll(name: str, audio_int16) -> str:
    """Enroll (or update) a speaker profile from one utterance. Returns a reply."""
    if not is_available():
        return (
            "Speaker identification isn't installed. "
            "Run: pip install resemblyzer — then try again."
        )
    if audio_int16 is None or len(audio_int16) < int(MIN_AUDIO_SECONDS * SAMPLE_RATE):
        return "That was too short to learn your voice. Please speak for a couple of seconds."

    name = name.strip().capitalize()
    try:
        emb = _embed(audio_int16)
    except Exception as e:
        log.error(f"Voice enrollment failed: {e}")
        return "I couldn't process your voice sample. Please try again."

    profiles = _load_profiles()
    if name in profiles:
        # average with existing profile so repeat enrollments refine it
        old = profiles[name]
        emb = [(o + n) / 2.0 for o, n in zip(old, emb)]
    profiles[name] = emb
    _save_profiles(profiles)
    log.info(f"Speaker enrolled: {name} ({len(profiles)} profiles total)")
    return f"Got it, {name}. I'll recognize your voice from now on."


def identify(audio_int16) -> tuple[Optional[str], float]:
    """Match an utterance against enrolled profiles.

    Returns (name, score) on a match, (None, best_score) otherwise.
    """
    if not is_available():
        return None, 0.0
    profiles = _load_profiles()
    if not profiles:
        return None, 0.0
    if audio_int16 is None or len(audio_int16) < int(MIN_AUDIO_SECONDS * SAMPLE_RATE):
        return None, 0.0

    try:
        emb = _embed(audio_int16)
    except Exception as e:
        log.warning(f"Speaker identification failed: {e}")
        return None, 0.0

    best_name, best_score = None, -1.0
    for name, ref in profiles.items():
        score = _cosine(emb, ref)
        if score > best_score:
            best_name, best_score = name, score

    if best_score >= config.SPEAKER_THRESHOLD:
        log.info(f"Speaker identified: {best_name} (score={best_score:.2f})")
        return best_name, best_score

    log.info(f"Speaker unknown (best={best_name} score={best_score:.2f} < threshold)")
    return None, best_score
