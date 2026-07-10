"""Tests for auto-detect language clamping (fixes accented-English mis-detection).

Short, accented utterances make faster-whisper guess exotic languages
(English heard as Arabic/Turkish). The clamp restricts auto-detect to the
languages Plasma actually supports (en, de) so transcription stays in the
right script and skill triggers keep matching.
"""
import pytest

np = pytest.importorskip("numpy")

from backend.modules.voice.asr import WhisperASR


class _FakeModel:
    """Stand-in for faster_whisper.WhisperModel with scripted detection."""

    def __init__(self, top, all_probs):
        self._top = top
        self._all = all_probs
        self.transcribe_lang = "unset"

    def detect_language(self, audio):
        return self._top[0], self._top[1], self._all

    def transcribe(self, audio, language=None, **kwargs):
        # record what language the caller forced, return a trivial segment list
        self.transcribe_lang = language

        class _Seg:
            text = "ok"

        class _Info:
            def __init__(self, lang):
                self.language = language or "auto"
                self.duration = 1.0

        return [_Seg()], _Info(language)


def _asr_with(model):
    asr = WhisperASR.__new__(WhisperASR)  # skip __init__ (no model download)
    asr.model = model
    asr.model_name = "small"
    return asr


def _audio():
    return (np.zeros(16000, dtype=np.int16))


def test_clamp_snaps_arabic_to_english():
    # "remember my voice as Hocine" mis-detected as Arabic; en is 2nd best
    model = _FakeModel(top=("ar", 0.48), all_probs=[("ar", 0.48), ("en", 0.30), ("de", 0.10)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language=None, allowed_languages=["en", "de"])
    assert model.transcribe_lang == "en"


def test_clamp_keeps_allowed_detection():
    model = _FakeModel(top=("de", 0.80), all_probs=[("de", 0.80), ("en", 0.15)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language=None, allowed_languages=["en", "de"])
    assert model.transcribe_lang == "de"


def test_clamp_picks_best_allowed_when_top_excluded():
    # top is Turkish; de outranks en among the allowed set
    model = _FakeModel(top=("tr", 0.40), all_probs=[("tr", 0.40), ("de", 0.25), ("en", 0.12)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language=None, allowed_languages=["en", "de"])
    assert model.transcribe_lang == "de"


def test_no_clamp_when_language_forced():
    model = _FakeModel(top=("ar", 0.9), all_probs=[("ar", 0.9)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language="en", allowed_languages=["en", "de"])
    # forced language must win; detect_language is never consulted
    assert model.transcribe_lang == "en"


def test_no_allowed_set_falls_back_to_full_auto():
    model = _FakeModel(top=("ar", 0.9), all_probs=[("ar", 0.9)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language=None, allowed_languages=None)
    assert model.transcribe_lang is None  # unrestricted auto-detect


def test_detect_failure_falls_back_to_auto():
    class _Boom(_FakeModel):
        def detect_language(self, audio):
            raise RuntimeError("no features")

    model = _Boom(top=("en", 1.0), all_probs=[("en", 1.0)])
    asr = _asr_with(model)
    asr.transcribe(_audio(), language=None, allowed_languages=["en", "de"])
    assert model.transcribe_lang is None  # graceful fallback
