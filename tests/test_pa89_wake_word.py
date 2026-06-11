"""PA-89 — Custom "Hey Plasma" wake word: training pipeline + runtime tests."""
from __future__ import annotations

import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Inject a stub openwakeword into sys.modules so wake_word.py can be imported
# even without the real package installed, and regardless of which other test
# file ran first and may have blanked backend.modules.voice in sys.modules.
# ---------------------------------------------------------------------------
_oww_pkg = types.ModuleType("openwakeword")
_oww_model_mod = types.ModuleType("openwakeword.model")
_oww_model_mod.Model = MagicMock(name="ModelClass")  # overridden per-test
sys.modules.setdefault("openwakeword", _oww_pkg)
sys.modules.setdefault("openwakeword.model", _oww_model_mod)

# Import wake_word NOW, before any other test may clobber the package namespace.
# Registering it in sys.modules makes patch.object reliable in any run order.
import importlib
import backend.modules.voice.wake_word as _ww  # noqa: E402
importlib.reload(_ww)  # re-run module body with our stub in place


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_model(wake_word: str, score: float = 0.0) -> MagicMock:
    m = MagicMock()
    m.predict.return_value = {wake_word: score}
    return m


def _audio_chunk(n: int = 1280) -> np.ndarray:
    return np.random.randint(-500, 500, n, dtype=np.int16)


def _make_detector(wake_word="hey_jarvis", threshold=0.5, model_path=None,
                   fake_score=0.0):
    """Build a WakeWordDetector with a mock Model."""
    score_key = Path(model_path).stem if (model_path and Path(model_path).exists()) else wake_word
    fake = _make_fake_model(score_key, fake_score)
    with patch.object(_ww, "Model", return_value=fake) as MockModel:
        det = _ww.WakeWordDetector(
            wake_word=wake_word,
            threshold=threshold,
            model_path=model_path,
        )
    det._mock_model_cls = MockModel
    det._fake_model_instance = fake
    return det


# ---------------------------------------------------------------------------
# WakeWordDetector — pre-trained model (by name)
# ---------------------------------------------------------------------------

class TestWakeWordDetectorNamed:
    def test_uses_name_as_key(self):
        det = _make_detector(wake_word="hey_jarvis")
        assert det.wake_word == "hey_jarvis"

    def test_no_detection_below_threshold(self):
        det = _make_detector(wake_word="hey_jarvis", threshold=0.5, fake_score=0.3)
        result = det.process(_audio_chunk(1280))
        assert result["detected"] is False
        assert result["score"] == pytest.approx(0.3, abs=1e-6)

    def test_detection_at_threshold(self):
        det = _make_detector(wake_word="hey_jarvis", threshold=0.5, fake_score=0.6)
        result = det.process(_audio_chunk(1280))
        assert result["detected"] is True

    def test_cooldown_suppresses_second_detection(self):
        det = _make_detector(wake_word="hey_jarvis", threshold=0.5, fake_score=0.9)
        det.cooldown_samples = 24_000  # force long cooldown
        r1 = det.process(_audio_chunk(1280))
        assert r1["detected"] is True
        r2 = det.process(_audio_chunk(1280))
        assert r2["detected"] is False

    def test_reset_clears_cooldown_and_buffer(self):
        det = _make_detector(wake_word="hey_jarvis", threshold=0.5, fake_score=0.9)
        det.cooldown_samples = 24_000
        det.process(_audio_chunk(1280))  # triggers, enters cooldown
        det.reset()
        assert det._cooldown_remaining == 0
        assert len(det._buffer) == 0

    def test_partial_chunk_buffered_not_processed(self):
        det = _make_detector(wake_word="hey_jarvis", threshold=0.5, fake_score=0.9)
        det.process(_audio_chunk(500))   # < OWW_FRAME (1280)
        det._fake_model_instance.predict.assert_not_called()
        assert len(det._buffer) == 500

    def test_model_loaded_with_name(self):
        fake = _make_fake_model("hey_jarvis", 0.0)
        with patch.object(_ww, "Model", return_value=fake) as MockModel:
            _ww.WakeWordDetector(wake_word="hey_jarvis")
        MockModel.assert_called_once_with(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx",
        )


# ---------------------------------------------------------------------------
# WakeWordDetector — custom model path (PA-89)
# ---------------------------------------------------------------------------

class TestWakeWordDetectorCustomPath:
    def test_uses_stem_as_score_key(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        det = _make_detector(wake_word="hey_jarvis", model_path=str(model_file))
        assert det.wake_word == "hey_plasma"

    def test_model_loaded_from_file_path(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        fake = _make_fake_model("hey_plasma", 0.0)
        with patch.object(_ww, "Model", return_value=fake) as MockModel:
            _ww.WakeWordDetector(wake_word="hey_jarvis", model_path=str(model_file))
        MockModel.assert_called_once_with(
            wakeword_models=[str(model_file)],
            inference_framework="onnx",
        )

    def test_detects_via_stem_key(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        det = _make_detector(model_path=str(model_file), threshold=0.5, fake_score=0.8)
        result = det.process(_audio_chunk(1280))
        assert result["detected"] is True

    def test_missing_path_falls_back_to_named(self, tmp_path):
        missing = str(tmp_path / "nonexistent.onnx")
        fake = _make_fake_model("hey_jarvis", 0.0)
        with patch.object(_ww, "Model", return_value=fake) as MockModel:
            det = _ww.WakeWordDetector(wake_word="hey_jarvis", model_path=missing)
        assert det.wake_word == "hey_jarvis"
        MockModel.assert_called_once_with(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx",
        )

    def test_no_model_path_uses_named_model(self):
        fake = _make_fake_model("hey_jarvis", 0.0)
        with patch.object(_ww, "Model", return_value=fake) as MockModel:
            det = _ww.WakeWordDetector(wake_word="hey_jarvis")
        assert det.wake_word == "hey_jarvis"
        MockModel.assert_called_once_with(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx",
        )

    def test_arbitrary_stem_name(self, tmp_path):
        model_file = tmp_path / "my_word.onnx"
        model_file.write_bytes(b"x")
        det = _make_detector(model_path=str(model_file), threshold=0.5, fake_score=0.7)
        assert det.wake_word == "my_word"
        assert det.process(_audio_chunk(1280))["detected"] is True


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_has_wake_word_model_path():
    from backend.core.config import config
    assert hasattr(config, "WAKE_WORD_MODEL_PATH")
    assert isinstance(config.WAKE_WORD_MODEL_PATH, str)


def test_config_wake_word_model_path_default_empty():
    import os
    from backend.core.config import config
    if "WAKE_WORD_MODEL_PATH" not in os.environ:
        assert config.WAKE_WORD_MODEL_PATH == ""


# ---------------------------------------------------------------------------
# WakeMonitor — passes model_path
# ---------------------------------------------------------------------------

def test_wake_monitor_source_passes_model_path():
    """Wake monitor source code wires WAKE_WORD_MODEL_PATH → WakeWordDetector."""
    src = Path(ROOT / "backend" / "modules" / "voice" / "wake_monitor.py").read_text()
    assert "WAKE_WORD_MODEL_PATH" in src
    assert "model_path=" in src


# ---------------------------------------------------------------------------
# Training script — structure and logic tests (no actual training)
# ---------------------------------------------------------------------------

class TestTrainingScript:
    def test_script_exists(self):
        assert (ROOT / "scripts" / "train_hey_plasma.py").exists()

    def test_has_main(self):
        import scripts.train_hey_plasma as t
        assert callable(t.main)

    def test_has_generate_samples(self):
        import scripts.train_hey_plasma as t
        assert callable(t.generate_samples)

    def test_has_train_model(self):
        import scripts.train_hey_plasma as t
        assert callable(t.train_model)

    def test_constants_defined(self):
        import scripts.train_hey_plasma as t
        assert t.SAMPLE_RATE == 16_000
        assert t.PHRASE == "hey plasma"
        assert len(t._VARIATIONS) >= 8

    def test_make_synthetic_clip_shape(self):
        import scripts.train_hey_plasma as t
        clip = t._make_synthetic_clip(speed=1.0, pitch_shift=0.0)
        assert len(clip) > 8_000
        assert clip.dtype == np.float32

    def test_make_synthetic_clip_amplitude(self):
        import scripts.train_hey_plasma as t
        clip = t._make_synthetic_clip()
        assert clip.max() <= 1.0
        assert clip.min() >= -1.0

    def test_generate_samples_writes_wavs(self, tmp_path, monkeypatch):
        import scripts.train_hey_plasma as t
        monkeypatch.setattr(t, "POSITIVE_DIR", tmp_path / "positive")
        monkeypatch.setattr(t, "_try_tts_clip", lambda *a, **kw: None)
        n = t.generate_samples(n=5, use_tts=False)
        assert n == 5
        wavs = list((tmp_path / "positive").glob("*.wav"))
        assert len(wavs) == 5

    def test_write_wav_produces_valid_file(self, tmp_path):
        import scripts.train_hey_plasma as t
        audio = np.zeros(1600, dtype=np.float32)
        dest = tmp_path / "test.wav"
        t._write_wav(dest, audio)
        with wave.open(str(dest)) as wf:
            assert wf.getframerate() == 16_000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getnframes() == 1600

    def test_train_no_samples_returns_false(self, tmp_path, monkeypatch):
        import scripts.train_hey_plasma as t
        monkeypatch.setattr(t, "POSITIVE_DIR", tmp_path / "empty")
        (tmp_path / "empty").mkdir()
        assert t.train_model() is False

    def test_train_without_tf_returns_false(self, tmp_path, monkeypatch):
        import scripts.train_hey_plasma as t
        pos = tmp_path / "positive"
        pos.mkdir()
        (pos / "sample.wav").write_bytes(b"RIFF")
        monkeypatch.setattr(t, "POSITIVE_DIR", pos)
        monkeypatch.setattr(t, "MODELS_DIR", tmp_path / "models")
        with patch.dict(sys.modules, {"openwakeword.train": None}):
            result = t.train_model()
        assert result is False

    def test_samples_named_correctly(self, tmp_path, monkeypatch):
        import scripts.train_hey_plasma as t
        pos = tmp_path / "positive"
        monkeypatch.setattr(t, "POSITIVE_DIR", pos)
        monkeypatch.setattr(t, "_try_tts_clip", lambda *a, **kw: None)
        t.generate_samples(n=3, use_tts=False)
        names = sorted(p.name for p in pos.glob("*.wav"))
        assert names == ["hey_plasma_0000.wav", "hey_plasma_0001.wav", "hey_plasma_0002.wav"]

    def test_variations_cover_speed_range(self):
        import scripts.train_hey_plasma as t
        speeds = [v[0] for v in t._VARIATIONS]
        assert min(speeds) < 0.90
        assert max(speeds) > 1.10

    def test_variations_cover_pitch_range(self):
        import scripts.train_hey_plasma as t
        pitches = [v[1] for v in t._VARIATIONS]
        assert min(pitches) < -3.0
        assert max(pitches) > 3.0

    def test_env_example_documents_model_path(self):
        text = (ROOT / ".env.example").read_text()
        assert "WAKE_WORD_MODEL_PATH" in text
        assert "hey_plasma.onnx" in text


# ---------------------------------------------------------------------------
# Integration: end-to-end detection flow with custom model
# ---------------------------------------------------------------------------

class TestEndToEndCustomModel:
    def test_full_detection_cycle(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        det = _make_detector(
            wake_word="hey_jarvis",
            threshold=0.5,
            model_path=str(model_file),
            fake_score=0.75,
        )
        assert det.wake_word == "hey_plasma"
        result = det.process(_audio_chunk(1280))
        assert result["detected"] is True
        assert result["score"] == pytest.approx(0.75, abs=1e-6)

    def test_score_below_threshold_no_detection(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        det = _make_detector(model_path=str(model_file), threshold=0.5, fake_score=0.1)
        assert det.process(_audio_chunk(1280))["detected"] is False

    def test_multiple_frames_accumulated(self, tmp_path):
        model_file = tmp_path / "hey_plasma.onnx"
        model_file.write_bytes(b"fake-onnx")
        det = _make_detector(model_path=str(model_file), threshold=0.5, fake_score=0.0)
        # Feed 3 × 1280 samples — predict should be called 3 times
        for _ in range(3):
            det.process(_audio_chunk(1280))
        assert det._fake_model_instance.predict.call_count == 3
