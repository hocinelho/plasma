"""She must speak with a voice that is present, not only a configured one.

scripts/download_female_voice.py puts a .onnx into voices/, and TTS then
refused to start until TTS_VOICE_MODEL was *also* set in .env. The result was
silence with the reason only in the server log — which reads as a broken app
rather than an unfinished setup.
"""
import pytest

from backend.core.config import config
from backend.modules.voice import tts


@pytest.fixture
def voices_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "VOICES_DIR", tmp_path)
    monkeypatch.setattr(config, "TTS_VOICE_MODEL", "")
    monkeypatch.setattr(tts, "_voice", None)
    return tmp_path


def test_a_downloaded_voice_is_used_without_touching_env(voices_dir):
    (voices_dir / "en_US-kristin-medium.onnx").write_bytes(b"fake")
    assert tts._default_voice_path().name == "en_US-kristin-medium.onnx"


def test_english_wins_when_several_are_present(voices_dir):
    (voices_dir / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
    (voices_dir / "en_US-amy-medium.onnx").write_bytes(b"x")
    assert tts._default_voice_path().name == "en_US-amy-medium.onnx"


def test_the_choice_is_stable_between_runs(voices_dir):
    """Alphabetical, not filesystem order — she must not change voice at random."""
    for name in ("en_US-zoe.onnx", "en_US-amy.onnx", "en_GB-alan.onnx"):
        (voices_dir / name).write_bytes(b"x")
    assert tts._default_voice_path().name == "en_GB-alan.onnx"
    assert tts._default_voice_path().name == "en_GB-alan.onnx"


def test_a_non_english_voice_is_better_than_none(voices_dir):
    (voices_dir / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
    assert tts._default_voice_path().name == "de_DE-thorsten-medium.onnx"


def test_no_voices_at_all(voices_dir):
    assert tts._default_voice_path() is None


def test_the_error_says_how_to_get_a_voice(voices_dir):
    with pytest.raises(RuntimeError) as e:
        tts._load_voice()
    msg = str(e.value)
    assert "download_female_voice.py" in msg
    # The old message named a setting, which sent people editing .env when
    # what they actually lacked was the file.
    assert "TTS_VOICE_MODEL not set" not in msg


def test_an_explicit_setting_still_wins(voices_dir, monkeypatch):
    (voices_dir / "en_US-amy.onnx").write_bytes(b"x")
    monkeypatch.setattr(config, "TTS_VOICE_MODEL", "voices/chosen.onnx")
    # _load_voice resolves the configured path; it must not silently prefer
    # the folder scan, or a deliberate choice would be ignored.
    with pytest.raises(FileNotFoundError) as e:
        tts._load_voice()
    assert "chosen.onnx" in str(e.value)


def test_silence_is_explained_to_the_browser():
    """The reason lives in the server log, where no user is looking."""
    import pathlib
    main = (pathlib.Path(tts.__file__).parents[3] / "backend" / "main.py")
    src = main.read_text(encoding="utf-8")
    assert '"tts_error": tts_error,' in src

    index = (pathlib.Path(tts.__file__).parents[3] / "frontend" / "index.html")
    page = index.read_text(encoding="utf-8")
    assert "data.tts_error" in page
    assert "__ttsErrorShown" in page          # once per session, not every turn
