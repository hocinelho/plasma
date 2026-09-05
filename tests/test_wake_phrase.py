"""She answers to "Hey Jarvis", and nobody could tell.

The custom "Hey Plasma" model needs training (TensorFlow, one-time), and
until it exists the wake word falls back to a pre-trained openWakeWord model
answering to a completely different phrase. That fallback WAS logged — as one
WARNING, a couple of hundred lines above where anyone looks, in a startup
that prints every trigger of all 49 skills.

So the single most important fact about talking to her hands-free was in
practice invisible: you say "Hey Plasma", nothing happens, and nothing
anywhere tells you why. Everything else about her can be found by trying it.
This cannot.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.modules.voice.wake_monitor import _announce_the_wake_phrase  # noqa: E402


class TestItSaysThePhrase:
    def test_it_names_the_phrase_that_actually_works(self, capsys, monkeypatch):
        from backend.core.config import config
        monkeypatch.setattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
        _announce_the_wake_phrase(wake_ok=True, clap_ok=False)
        out = capsys.readouterr().out
        assert "HEY JARVIS" in out

    def test_it_says_which_phrase_does_NOT_work(self, capsys, monkeypatch):
        """Naming the right phrase is not enough when the user already has a
        wrong one in mind and has been saying it for days."""
        from backend.core.config import config
        monkeypatch.setattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
        _announce_the_wake_phrase(wake_ok=True, clap_ok=False)
        out = capsys.readouterr().out
        assert 'not "hey plasma"' in out.lower()

    def test_it_points_at_the_way_to_get_the_real_one(self, capsys, monkeypatch):
        from backend.core.config import config
        monkeypatch.setattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
        _announce_the_wake_phrase(wake_ok=True, clap_ok=False)
        assert "train_hey_plasma.py" in capsys.readouterr().out

    def test_a_trained_model_is_reported_without_the_warning(self, capsys, monkeypatch):
        """Once it is trained, the correction is noise — she does answer to
        her own name."""
        from backend.core.config import config
        monkeypatch.setattr(config, "WAKE_WORD_MODEL", "hey_plasma")
        _announce_the_wake_phrase(wake_ok=True, clap_ok=False)
        out = capsys.readouterr().out
        assert "train_hey_plasma.py" not in out
        assert "hey_plasma" in out

    def test_clapping_is_mentioned_when_it_is_on(self, capsys, monkeypatch):
        from backend.core.config import config
        monkeypatch.setattr(config, "WAKE_WORD_MODEL", "hey_jarvis")
        _announce_the_wake_phrase(wake_ok=True, clap_ok=True)
        assert "clap" in capsys.readouterr().out.lower()

    def test_no_hands_free_at_all_says_what_to_do_instead(self, capsys):
        _announce_the_wake_phrase(wake_ok=False, clap_ok=False)
        out = capsys.readouterr().out
        assert "tap her" in out.lower()

    def test_it_is_printed_not_only_logged(self):
        """The fallback was already a log.warning and that is exactly how it
        went unnoticed — buried in the skill-loading wall of text."""
        src = (ROOT / "backend" / "modules" / "voice" / "wake_monitor.py").read_text(
            encoding="utf-8")
        body = src.split("def _announce_the_wake_phrase", 1)[1].split("\ndef ", 1)[0]
        assert "print(" in body

    def test_the_monitor_calls_it_on_start(self):
        src = (ROOT / "backend" / "modules" / "voice" / "wake_monitor.py").read_text(
            encoding="utf-8")
        assert "_announce_the_wake_phrase(wake_ok, clap_ok)" in src


class TestTheDoctorSaysItToo:
    def test_it_has_a_wake_word_check(self):
        src = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
        assert "def check_wake_word()" in src
        assert "check_wake_word" in src.split("def main()", 1)[1]

    def test_the_check_names_both_phrases(self):
        src = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
        block = src.split("def check_wake_word()", 1)[1].split("\ndef ", 1)[0]
        assert "Hey Jarvis" in block
        assert "Hey Plasma" in block

    def test_the_old_misleading_check_is_gone(self):
        """It said 'hey Plasma won't work (push-to-talk still does)', which
        is wrong twice: the wake word DOES work, under another phrase, and
        clapping works too."""
        src = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
        assert "push-to-talk still does" not in src
