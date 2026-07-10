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


# openWakeWord feature pipeline constants.  The wake word classifier that
# openWakeWord loads at runtime expects an input of shape [N, 16, 96]:
# 16 embedding frames, 96 dims each.  Each embedding is produced from a
# 76-frame mel-spectrogram window, sliding with a stride of 8 mel frames.
N_EMB = 16            # embedding frames per classifier input
EMB_DIM = 96          # embedding model output dim
MEL_WINDOW = 76       # mel frames per embedding
MEL_STRIDE = 8        # mel-frame stride between consecutive embeddings
MEL_FRAMES_NEEDED = (N_EMB - 1) * MEL_STRIDE + MEL_WINDOW  # = 196
TRAIN_AUDIO_LEN = 32_000  # 2 s @ 16 kHz — enough to yield 196 mel frames


def _load_wav_raw(path: Path) -> np.ndarray:
    """Load a WAV as float32 mono 16 kHz in the raw int16 value range.

    openWakeWord's melspectrogram model expects the int16 sample values cast
    to float32 (NOT normalised to [-1, 1]), so we deliberately do not divide.
    """
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        data = wf.readframes(n)
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if sr != SAMPLE_RATE:
        from scipy.signal import resample
        audio = resample(audio, int(len(audio) * SAMPLE_RATE / sr)).astype(np.float32)
    return audio


def _place_in_window(audio: np.ndarray, target: int = TRAIN_AUDIO_LEN) -> np.ndarray:
    """Randomly place a clip inside a fixed-length window (zeros around it)."""
    if len(audio) >= target:
        return audio[:target]
    pad_total = target - len(audio)
    pre = random.randint(0, pad_total)
    post = pad_total - pre
    return np.concatenate([
        np.zeros(pre, dtype=np.float32),
        audio,
        np.zeros(post, dtype=np.float32),
    ])


def _extract_features_oww(wav_files: list[Path], melspec_path: str,
                          embedding_path: str) -> np.ndarray:
    """Extract openWakeWord [N, 16, 96] features from WAV files.

    Chains the bundled melspectrogram model -> embedding model exactly the
    way openWakeWord does internally, so the resulting classifier is loadable
    by openwakeword.model.Model at runtime.
    """
    import onnxruntime as ort
    mel_sess = ort.InferenceSession(melspec_path)
    emb_sess = ort.InferenceSession(embedding_path)
    mel_in = mel_sess.get_inputs()[0].name
    emb_in = emb_sess.get_inputs()[0].name

    out = []
    for wav_path in wav_files:
        audio = _place_in_window(_load_wav_raw(wav_path))

        # melspectrogram: [1, L] -> squeeze -> [n_frames, 32]
        mel = mel_sess.run(None, {mel_in: audio[None, :].astype(np.float32)})[0]
        mel = np.squeeze(mel)
        if mel.ndim != 2:           # some exports return [1,1,frames,32]
            mel = mel.reshape(-1, 32)
        mel = mel / 10.0 + 2.0       # openWakeWord normalisation
        if mel.shape[0] < MEL_FRAMES_NEEDED:
            mel = np.pad(mel, ((0, MEL_FRAMES_NEEDED - mel.shape[0]), (0, 0)))

        # 16 embeddings from sliding 76-frame windows
        embs = []
        for i in range(N_EMB):
            start = i * MEL_STRIDE
            window = mel[start:start + MEL_WINDOW]            # [76, 32]
            window = window[None, :, :, None].astype(np.float32)  # [1,76,32,1]
            e = emb_sess.run(None, {emb_in: window})[0].squeeze()  # [96]
            embs.append(e[:EMB_DIM])
        out.append(np.stack(embs))   # [16, 96]

    return np.array(out, dtype=np.float32)  # [N, 16, 96]


# Phrases used to synthesise speech-like negatives so the model learns to
# fire on "hey plasma" specifically, not on any speech.
_NEGATIVE_PHRASES = [
    "hello there", "what time is it", "play some music", "the weather today",
    "open the door", "how are you", "good morning", "turn it off",
    "set a timer", "thank you very much", "see you later", "what is this",
    "hey google", "hey siri", "okay computer", "hey jarvis",
    "tell me a joke", "stop the music", "volume up", "next song",
    "hey there plasma is great", "plasma physics", "hey you", "playing now",
    "let me think", "i don't know", "maybe tomorrow", "call my friend",
]


def _generate_negative_wavs(neg_dir: Path, n_speech: int, n_noise: int) -> None:
    """Create speech-like and noise negatives into neg_dir."""
    neg_dir.mkdir(parents=True, exist_ok=True)
    from scipy.signal import resample

    # Speech-like negatives via TTS (skipped if no TTS engine)
    written = 0
    base_clips = []
    for phrase in _NEGATIVE_PHRASES:
        clip = _try_tts_clip(phrase)
        if clip is not None:
            base_clips.append(clip)

    if base_clips:
        i = 0
        while written < n_speech:
            base = random.choice(base_clips)
            speed = random.uniform(0.85, 1.15)
            clip = resample(base, max(1, int(len(base) / speed))).astype(np.float32)
            clip = np.clip(clip + np.random.normal(0, 0.01, len(clip)), -1.0, 1.0)
            _write_wav(neg_dir / f"neg_speech_{i:04d}.wav", clip)
            written += 1
            i += 1
    else:
        log.info("No TTS engine for speech negatives — using noise only")
        n_noise += n_speech

    # Noise negatives
    for i in range(n_noise):
        dur = random.uniform(0.4, 1.6)
        noise = np.random.normal(0, random.uniform(0.02, 0.08),
                                 int(SAMPLE_RATE * dur)).astype(np.float32)
        noise = np.clip(noise, -1.0, 1.0)
        _write_wav(neg_dir / f"neg_noise_{i:04d}.wav", noise)


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

    # ── Step 1: TF + openWakeWord models ─────────────────────────────────
    try:
        import tensorflow as tf
        tf.get_logger().setLevel("ERROR")
    except ImportError:
        _print_tf_instructions()
        return False

    melspec_path, embedding_path = _find_oww_models()
    if not (melspec_path and embedding_path):
        log.error(
            "openWakeWord's bundled melspec/embedding models were not found. "
            "Run: python -c \"import openwakeword; openwakeword.utils.download_models()\""
        )
        return False
    log.info(f"Using openWakeWord embedding pipeline ({Path(embedding_path).name})")

    # ── Step 2: Positive features ────────────────────────────────────────
    features_pos = _extract_features_oww(positive_wavs, melspec_path, embedding_path)
    log.info(f"Positive features: {features_pos.shape}")  # [N, 16, 96]

    # ── Step 3: Negative features (speech + noise) ───────────────────────
    neg_dir = TRAIN_DIR / "negative"
    n_pos = len(features_pos)
    _generate_negative_wavs(neg_dir, n_speech=n_pos * 2, n_noise=n_pos)
    neg_wavs = sorted(neg_dir.glob("*.wav"))
    features_neg = _extract_features_oww(neg_wavs, melspec_path, embedding_path)
    log.info(f"Negative features: {features_neg.shape}")

    # ── Step 4: Dataset ──────────────────────────────────────────────────
    X = np.concatenate([features_pos, features_neg])           # [M, 16, 96]
    y = np.concatenate([
        np.ones(len(features_pos), dtype=np.float32),
        np.zeros(len(features_neg), dtype=np.float32),
    ])
    idx = np.random.permutation(len(X))
    X, y = X[idx], y[idx]

    # ── Step 5: Train classifier (input [16, 96]) ────────────────────────
    log.info(f"Training classifier on {len(X)} samples...")
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(N_EMB, EMB_DIM)),
        tf.keras.layers.Flatten(),
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

    # ── Step 6: Export to ONNX (manual — robust across TF/Keras versions) ─
    _export_onnx_manual(model, OUTPUT_MODEL)

    if OUTPUT_MODEL.exists():
        _print_env_instructions(OUTPUT_MODEL)
        return True

    log.error("Training finished but hey_plasma.onnx not found")
    return False


def _export_onnx_manual(keras_model, output_path: Path) -> None:
    """Build an openWakeWord-compatible ONNX model from the Keras weights.

    Input:  [batch, 16, 96]   (matches openWakeWord's classifier contract)
    Output: [batch, 1]        (wake word probability)

    Built by hand so it doesn't depend on tf2onnx, which breaks with Keras 3.
    """
    import onnx
    from onnx import helper, TensorProto, numpy_helper

    # Dense weights only (Flatten/Dropout carry none)
    dense_weights = [w for w in keras_model.get_weights()]
    n_dense = len(dense_weights) // 2

    nodes = []
    initializers = []

    # Reshape [batch,16,96] -> [batch, 1536]
    flat_dim = N_EMB * EMB_DIM
    shape_name = "reshape_shape"
    initializers.append(numpy_helper.from_array(
        np.array([-1, flat_dim], dtype=np.int64), shape_name))
    nodes.append(helper.make_node("Reshape", ["input", shape_name], ["flat"]))
    current = "flat"

    for d in range(n_dense):
        W = dense_weights[2 * d].astype(np.float32)      # [in, out]
        b = dense_weights[2 * d + 1].astype(np.float32)  # [out]
        w_name, b_name = f"W{d}", f"b{d}"
        mm_name, add_name = f"matmul_{d}", f"add_{d}"
        initializers.append(numpy_helper.from_array(W, w_name))
        initializers.append(numpy_helper.from_array(b, b_name))
        nodes.append(helper.make_node("MatMul", [current, w_name], [mm_name]))
        nodes.append(helper.make_node("Add", [mm_name, b_name], [add_name]))
        if d < n_dense - 1:
            relu_name = f"relu_{d}"
            nodes.append(helper.make_node("Relu", [add_name], [relu_name]))
            current = relu_name
        else:
            nodes.append(helper.make_node("Sigmoid", [add_name], ["output"]))

    X = helper.make_tensor_value_info("input", TensorProto.FLOAT, ["batch", N_EMB, EMB_DIM])
    Y = helper.make_tensor_value_info("output", TensorProto.FLOAT, ["batch", 1])
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
