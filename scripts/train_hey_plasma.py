"""
PA-89 — Train a custom "Hey Plasma" wake word model.

Pipeline:
  1. Generate synthetic positive audio clips ("Hey Plasma" in many variations)
  2. Run openWakeWord's training pipeline (requires TensorFlow)
  3. Export the trained model to .plasma/models/hey_plasma.onnx
  4. Update .env to point WAKE_WORD_MODEL_PATH at the new model

Usage:
    # Fully automatic (synthetic TTS samples):
    python scripts/train_hey_plasma.py

    # Use your own recordings for better accuracy:
    python scripts/train_hey_plasma.py --samples-dir path/to/wavs/

    # Just generate samples, skip training (inspect before training):
    python scripts/train_hey_plasma.py --samples-only

    # Skip generation, train from existing samples:
    python scripts/train_hey_plasma.py --train-only

Requirements:
    pip install tensorflow  # for training (one-time)
    The rest is already in requirements.txt (numpy, scipy, soundfile)

If TensorFlow is not available, this script will generate the data and
print instructions for finishing training in Google Colab.
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("plasma.train_wake")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLASMA_DIR = PROJECT_ROOT / ".plasma"
MODELS_DIR = PLASMA_DIR / "models"
TRAIN_DIR = PLASMA_DIR / "training" / "hey_plasma"
POSITIVE_DIR = TRAIN_DIR / "positive"
OUTPUT_MODEL = MODELS_DIR / "hey_plasma.onnx"

SAMPLE_RATE = 16_000
PHRASE = "hey plasma"

# Variations: (speed_factor, pitch_semitones)
_VARIATIONS: list[tuple[float, float]] = [
    (1.00,  0.0),
    (0.90, -2.0),
    (1.10, +2.0),
    (0.85, -4.0),
    (1.15, +3.0),
    (0.95, -1.0),
    (1.05, +1.0),
    (0.80, -3.0),
    (1.20, +4.0),
    (1.00, -5.0),
    (0.92, +2.5),
    (1.08, -2.5),
]


# ---------------------------------------------------------------------------
# Synthetic sample generation
# ---------------------------------------------------------------------------

def _sine_word(freq_hz: float, duration_s: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Sine-wave approximation of a spoken syllable (placeholder for real TTS)."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    signal = np.sin(2 * math.pi * freq_hz * t)
    # Add brief exponential envelope (attack + decay)
    envelope = np.exp(-3 * t / duration_s)
    return (signal * envelope * 0.8).astype(np.float32)


def _make_synthetic_clip(speed: float = 1.0, pitch_shift: float = 0.0) -> np.ndarray:
    """
    Build a crude "Hey Plasma" clip from sine waves.

    This is only a structural placeholder — real accuracy requires either:
      - Your own recordings
      - A real TTS engine (piper, gTTS, edge-tts)

    Frequency layout (rough phoneme approximation):
      "hey" ≈ 300 Hz, 0.25 s
      silence ≈ 0.05 s
      "plas" ≈ 200 Hz, 0.20 s
      "ma"  ≈ 180 Hz, 0.15 s
    """
    freq_base = 250.0 * (2 ** (pitch_shift / 12))
    hey  = _sine_word(freq_base * 1.2, 0.25 / speed)
    gap  = np.zeros(int(SAMPLE_RATE * 0.05 / speed), dtype=np.float32)
    plas = _sine_word(freq_base * 0.9, 0.20 / speed)
    ma   = _sine_word(freq_base * 0.8, 0.15 / speed)

    clip = np.concatenate([hey, gap, plas, ma])
    # Add low-level background noise for robustness
    noise = np.random.normal(0, 0.02, len(clip)).astype(np.float32)
    clip = np.clip(clip + noise, -1.0, 1.0)
    return clip


def _try_tts_clip(text: str = PHRASE) -> np.ndarray | None:
    """Try to use gTTS or pyttsx3 for a real TTS sample."""
    try:
        from gtts import gTTS
        import io
        import soundfile as sf
        buf = io.BytesIO()
        gTTS(text=text, lang="en").write_to_fp(buf)
        buf.seek(0)
        data, sr = sf.read(buf)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != SAMPLE_RATE:
            from scipy.signal import resample
            data = resample(data, int(len(data) * SAMPLE_RATE / sr)).astype(np.float32)
        return data.astype(np.float32)
    except Exception:
        pass

    try:
        import pyttsx3, tempfile, soundfile as sf
        engine = pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        data, sr = sf.read(tmp)
        Path(tmp).unlink(missing_ok=True)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != SAMPLE_RATE:
            from scipy.signal import resample
            data = resample(data, int(len(data) * SAMPLE_RATE / sr)).astype(np.float32)
        return data.astype(np.float32)
    except Exception:
        pass

    return None


def _write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def generate_samples(n: int = 200, use_tts: bool = True) -> int:
    """
    Generate N positive samples of "Hey Plasma" into POSITIVE_DIR.
    Returns number of clips written.
    """
    POSITIVE_DIR.mkdir(parents=True, exist_ok=True)

    tts_base = _try_tts_clip() if use_tts else None
    if tts_base is not None:
        log.info("Using TTS engine for realistic samples")
    else:
        log.info("No TTS engine found — using synthetic sine-wave samples. "
                 "Install gtts or pyttsx3 for better accuracy.")

    written = 0
    for i in range(n):
        speed, pitch = random.choice(_VARIATIONS)
        # Small extra random jitter per sample
        speed *= random.uniform(0.95, 1.05)
        pitch += random.uniform(-0.5, 0.5)

        if tts_base is not None:
            from scipy.signal import resample
            new_len = int(len(tts_base) / speed)
            clip = resample(tts_base, new_len).astype(np.float32)
            # Rough pitch shift via resampling trick
            if abs(pitch) > 0.1:
                ratio = 2 ** (pitch / 12)
                stretched = resample(clip, int(len(clip) * ratio)).astype(np.float32)
                clip = resample(stretched, len(clip)).astype(np.float32)
            noise = np.random.normal(0, 0.01, len(clip)).astype(np.float32)
            clip = np.clip(clip + noise, -1.0, 1.0)
        else:
            clip = _make_synthetic_clip(speed=speed, pitch_shift=pitch)

        dest = POSITIVE_DIR / f"hey_plasma_{i:04d}.wav"
        _write_wav(dest, clip)
        written += 1

    log.info(f"Generated {written} positive samples in {POSITIVE_DIR}")
    return written


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_model() -> bool:
    """
    Run openWakeWord training on the generated positive samples.
    Returns True if model saved successfully.
    """
    positive_wavs = sorted(POSITIVE_DIR.glob("*.wav"))
    if not positive_wavs:
        log.error(f"No WAV files in {POSITIVE_DIR} — run with --samples-only first")
        return False

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import openwakeword.train as oww_train
    except ImportError:
        _print_colab_instructions()
        return False

    try:
        log.info(f"Training on {len(positive_wavs)} positive samples...")
        oww_train.train(
            model_type="dnn",
            positive_training_data_dir=str(POSITIVE_DIR),
            output_dir=str(MODELS_DIR),
            model_name="hey_plasma",
            n_epochs=100,
        )

        onnx_path = MODELS_DIR / "hey_plasma.onnx"
        if onnx_path.exists():
            log.info(f"Model saved: {onnx_path}")
            _print_env_instructions(onnx_path)
            return True

        log.error("Training finished but hey_plasma.onnx not found in output dir")
        return False

    except Exception as e:
        log.error(f"Training failed: {e}")
        _print_colab_instructions()
        return False


def _print_env_instructions(model_path: Path) -> None:
    print(f"""
Model ready: {model_path}

Add to your .env:
  WAKE_WORD_ENABLED=true
  WAKE_WORD_MODEL_PATH={model_path}
  WAKE_WORD_THRESHOLD=0.5

Then restart Plasma.  Say "Hey Plasma" to trigger hands-free recording.
""")


def _print_colab_instructions() -> None:
    print("""
TensorFlow not found — training requires TF.

Quick options:
  1. pip install tensorflow  (then re-run this script)
  2. Use Google Colab:
       https://colab.research.google.com/
       Upload: .plasma/training/hey_plasma/positive/*.wav
       Use openWakeWord's training notebook:
       https://github.com/dscripka/openWakeWord#training-new-models
       Download the resulting hey_plasma.onnx to .plasma/models/

  Then set in .env:
    WAKE_WORD_MODEL_PATH=.plasma/models/hey_plasma.onnx
""")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Train Hey Plasma wake word model")
    parser.add_argument(
        "--samples-dir",
        help="Use your own WAV recordings instead of generating synthetic ones",
    )
    parser.add_argument(
        "--samples-only",
        action="store_true",
        help="Generate samples but skip training",
    )
    parser.add_argument(
        "--train-only",
        action="store_true",
        help="Skip sample generation, train from existing samples",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=200,
        help="Number of synthetic samples to generate (default: 200)",
    )
    args = parser.parse_args()

    if args.samples_dir:
        src = Path(args.samples_dir)
        if not src.is_dir():
            print(f"ERROR: {src} is not a directory", file=sys.stderr)
            sys.exit(1)
        POSITIVE_DIR.mkdir(parents=True, exist_ok=True)
        wavs = list(src.glob("*.wav"))
        if not wavs:
            print(f"ERROR: no WAV files in {src}", file=sys.stderr)
            sys.exit(1)
        for w in wavs:
            shutil.copy2(w, POSITIVE_DIR / w.name)
        log.info(f"Copied {len(wavs)} recordings to {POSITIVE_DIR}")
    elif not args.train_only:
        generate_samples(n=args.n_samples)

    if args.samples_only:
        print(f"\nSamples ready in {POSITIVE_DIR}")
        print("Run without --samples-only to train.")
        return

    ok = train_model()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
