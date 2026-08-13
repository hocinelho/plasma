"""Tests for summon mode (/?stage=1) — arriving on stage, already listening.

The behaviour itself is verified in a real browser; what is pinned here is the
wiring a browser test would not notice going missing: the query parameters the
iOS Shortcut depends on, and the wake event the stage listens for.

If the parameter name ever changes, every shortcut a user has already made
stops working silently — hence a test on the literal strings.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_stage_parameter_is_read():
    assert "params.get('stage') === '1'" in INDEX


def test_listen_can_be_opted_out():
    """?listen=0 must keep the mic shut for anyone who wants a tap first."""
    assert "params.get('listen') !== '0'" in INDEX


def test_summon_is_off_by_default():
    """A plain visit must behave exactly as it did before summon mode."""
    assert "if (!summoned) return;" in INDEX


def test_wake_is_broadcast_as_an_event():
    """The stage listens for this instead of reaching into the socket."""
    assert "new CustomEvent('plasma-wake'" in INDEX
    assert "addEventListener('plasma-wake'" in INDEX


def test_summon_waits_for_the_renderer_and_the_mic():
    """avatarStage() and mediaRecorder both appear late — firing early is a
    no-op that looks like the feature is broken."""
    assert "whenReady(() => !!window.avatarStage" in INDEX
    assert "whenReady(() => !!mediaRecorder" in INDEX


def test_summon_gives_up_rather_than_polling_forever():
    assert "performance.now() > deadline" in INDEX


def test_launcher_prints_the_summon_url():
    """It is the address people need on the phone — it should not be folklore."""
    launcher = (ROOT / "serve_phone.py").read_text(encoding="utf-8")
    assert "?stage=1" in launcher


def test_docs_cover_the_shortcut():
    doc = (ROOT / "docs" / "phone-setup.md").read_text(encoding="utf-8")
    assert "?stage=1" in doc
    assert "Open URLs" in doc          # the Shortcuts action people must find
