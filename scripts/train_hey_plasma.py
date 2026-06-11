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
# Training — uses openWakeWord's bundled embedding model + TF/Keras
# ---------------------------------------------------------------------------

def _find_oww_models() -> tuple[str, str]:
    """Find openWakeWord's bundled melspec + embedding ONNX models."""
    import openwakeword
    oww_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    melspec = None
    embedding = None
    for f in oww_dir.glob("*.onnx"):
        name = f.stem.lower()
        if "melspec" in name:
            melspec = str(f)
        elif "embedding" in name:
            embedding = str(f)
    if not melspec or not embedding:
        # Fallback: scan all .onnx and .tflite
        for f in oww_dir.iterdir():
            name = f.stem.lower()
            if "melspec" in name:
                melspec = str(f)
            elif "embedding" in name or "embed" in name:
                embedding = str(f)
    return melspec, embedding


def _load_wav_float(path: Path) -> np.ndarray:
    """Load a WAV file as float32 mono 16 kHz."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        data = wf.readframes(n)
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != SAMPLE_RATE:
        from scipy.signal import resample
        audio = resample(audio, int(len(audio) * SAMPLE_RATE / sr)).astype(np.float32)
    return audio


def _extract_embeddings_oww(wav_files: list[Path], melspec_path: str,
                             embedding_path: str, n_frames: int = 16
                             ) -> np.ndarray:
    """Extract embeddings from WAV files using openWakeWord's pipeline."""
    import onnxruntime as ort
    melspec_session = ort.InferenceSession(melspec_path)
    embed_session = ort.InferenceSession(embedding_path)

    mel_input_name = melspec_session.get_inputs()[0].name
    embed_input_name = embed_session.get_inputs()[0].name
    embed_output_dim = embed_session.get_outputs()[0].shape[-1]  # typically 96

    all_embeddings = []
    frame_size = 1280  # 80 ms at 16 kHz

    for wav_path in wav_files:
        audio = _load_wav_float(wav_path)
        # Pad to at least n_frames * frame_size
        min_len = n_frames * frame_size
        if len(audio) < min_len:
            audio = np.pad(audio, (0, min_len - len(audio)))

        embeddings = []
        for i in range(0, len(audio) - frame_size + 1, frame_size):
            chunk = audio[i:i + frame_size].reshape(1, -1)
            mel = melspec_session.run(None, {mel_input_name: chunk})[0]
            emb = embed_session.run(None, {embed_input_name: mel})[0]
            embeddings.append(emb.flatten()[:embed_output_dim])
            if len(embeddings) >= n_frames:
                break

        while len(embeddings) < n_frames:
            embeddings.append(np.zeros(embed_output_dim, dtype=np.float32))

        feature = np.concatenate(embeddings[:n_frames])
        all_embeddings.append(feature)

    return np.array(all_embeddings, dtype=np.float32)


def _extract_mel_features(wav_files: list[Path], n_mels: int = 32,
                           window_len: int = 24000) -> np.ndarray:
    """Fallback: direct mel-spectrogram features when openWakeWord models unavailable."""
    from scipy.signal import spectrogram

    all_features = []
    for wav_path in wav_files:
        audio = _load_wav_float(wav_path)
        if len(audio) < window_len:
            audio = np.pad(audio, (0, window_len - len(audio)))
        audio = audio[:window_len]

        _, _, Sxx = spectrogram(audio, fs=SAMPLE_RATE, nperseg=400, noverlap=240,
                                nfft=512, mode='magnitude')
        # Crude mel binning
        n_freq = Sxx.shape[0]
        bin_size = max(1, n_freq // n_mels)
        mel = np.array([Sxx[i*bin_size:(i+1)*bin_size].mean(axis=0)
                        for i in range(n_mels)])
        mel = np.log1p(mel).flatten().astype(np.float32)
        all_features.append(mel)

    return np.array(all_features, dtype=np.float32)


def train_model() -> bool:
    """
    Train a 'Hey Plasma' wake word model using openWakeWord's embedding
    pipeline + TensorFlow/Keras.  Returns True if model saved successfully.
    """
    positive_wavs = sorted(POSITIVE_DIR.glob("*.wav"))
    if not positive_wavs:
        log.error(f"No WAV files in {POSITIVE_DIR} — run with --samples-only first")
        return False

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Try to import TF ─────────────────────────────────────────
    try:
        import tensorflow as tf
        tf.get_logger().setLevel("ERROR")
    except ImportError:
        _print_tf_instructions()
        return False

    # ── Step 2: Extract features from positive samples ───────────────────
    use_oww = False
    n_frames = 16
    try:
        melspec_path, embedding_path = _find_oww_models()
        if melspec_path and embedding_path:
            log.info(f"Using openWakeWord embedding pipeline "
                     f"({Path(embedding_path).name})")
            features_pos = _extract_embeddings_oww(
                positive_wavs, melspec_path, embedding_path, n_frames
            )
            use_oww = True
        else:
            raise FileNotFoundError("openWakeWord models not found")
    except Exception as e:
        log.warning(f"openWakeWord embedding extraction failed: {e}")
        log.info("Falling back to direct mel-spectrogram features")
        features_pos = _extract_mel_features(positive_wavs)

    feature_dim = features_pos.shape[1]
    log.info(f"Positive features: {features_pos.shape} (dim={feature_dim})")

    # ── Step 3: Generate negative features ───────────────────────────────
    n_neg = len(features_pos) * 3
    neg_wavs_dir = TRAIN_DIR / "negative"
    neg_wavs_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n_neg):
        dur = random.uniform(0.4, 1.5)
        noise = np.random.normal(0, 0.05, int(SAMPLE_RATE * dur)).astype(np.float32)
        noise = np.clip(noise, -1.0, 1.0)
        _write_wav(neg_wavs_dir / f"neg_{i:04d}.wav", noise)

    neg_wavs = sorted(neg_wavs_dir.glob("*.wav"))
    if use_oww:
        features_neg = _extract_embeddings_oww(
            neg_wavs, melspec_path, embedding_path, n_frames
        )
    else:
        features_neg = _extract_mel_features(neg_wavs)

    log.info(f"Negative features: {features_neg.shape}")

    # ── Step 4: Build dataset ────────────────────────────────────────────
    X = np.concatenate([features_pos, features_neg])
    y = np.concatenate([
        np.ones(len(features_pos), dtype=np.float32),
        np.zeros(len(features_neg), dtype=np.float32),
    ])
    # Shuffle
    idx = np.random.permutation(len(X))
    X, y = X[idx], y[idx]

    # ── Step 5: Train Keras model ────────────────────────────────────────
    log.info(f"Training classifier on {len(X)} samples (dim={feature_dim})...")
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(feature_dim,)),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="binary_crossentropy",
                  metrics=["accuracy"])
    model.fit(X, y, epochs=100, batch_size=32, validation_split=0.2, verbose=0)

    loss, acc = model.evaluate(X, y, verbose=0)
    log.info(f"Training accuracy: {acc:.1%}")

    # ── Step 6: Export to ONNX ───────────────────────────────────────────
    try:
        import tf2onnx
        import onnx

        spec = (tf.TensorSpec((1, feature_dim), tf.float32, name="input"),)
        model_proto, _ = tf2onnx.convert.from_keras(model, input_signature=spec,
                                                      output_path=str(OUTPUT_MODEL))
        log.info(f"Model exported (tf2onnx): {OUTPUT_MODEL}")
    except ImportError:
        # Fallback: build ONNX manually from weights
        log.info("tf2onnx not found — building ONNX from weights directly")
        _export_onnx_manual(model, feature_dim, OUTPUT_MODEL)

    if OUTPUT_MODEL.exists():
        _print_env_instructions(OUTPUT_MODEL)
        return True

    log.error("Training finished but hey_plasma.onnx not found")
    return False


def _export_onnx_manual(keras_model, feature_dim: int, output_path: Path) -> None:
    """Build ONNX model manually from Keras weights (no tf2onnx needed)."""
    import onnx
    from onnx import helper, TensorProto, numpy_helper

    weights = keras_model.get_weights()
    # Layers: Dense(128), Dense(64), Dense(1) — each has [W, b]
    # With Dropout layers (no weights)

    nodes = []
    initializers = []
    layer_idx = 0
    input_name = "input"
    current = input_name

    dense_count = 0
    for i in range(0, len(weights), 2):
        W = weights[i]
        b = weights[i + 1]
        w_name = f"W{dense_count}"
        b_name = f"b{dense_count}"
        mm_name = f"matmul_{dense_count}"
        add_name = f"add_{dense_count}"

        initializers.append(numpy_helper.from_array(W.astype(np.float32), w_name))
        initializers.append(numpy_helper.from_array(b.astype(np.float32), b_name))

        nodes.append(helper.make_node("MatMul", [current, w_name], [mm_name]))
        nodes.append(helper.make_node("Add", [mm_name, b_name], [add_name]))

        if dense_count < len(weights) // 2 - 1:
            relu_name = f"relu_{dense_count}"
            nodes.append(helper.make_node("Relu", [add_name], [relu_name]))
            current = relu_name
        else:
            sig_name = "output"
            nodes.append(helper.make_node("Sigmoid", [add_name], [sig_name]))
            current = sig_name

        dense_count += 1

    X = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, feature_dim])
    Y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1])

    graph = helper.make_graph(nodes, "hey_plasma", [X], [Y], initializers)
    model_proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.save(model_proto, str(output_path))
    log.info(f"Model exported (manual ONNX): {output_path}")


def _print_env_instructions(model_path: Path) -> None:
    print(f"""
Model ready: {model_path}

Add to your .env:
  WAKE_WORD_ENABLED=true
  WAKE_WORD_MODEL_PATH={model_path}
  WAKE_WORD_THRESHOLD=0.5

Then restart Plasma.  Say "Hey Plasma" to trigger hands-free recording.
""")


def _print_tf_instructions() -> None:
    print("""
TensorFlow not found — required for training.

    pip install tensorflow

Then re-run this script.
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
