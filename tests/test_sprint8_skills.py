"""Tests for Sprint 8 skills: PA-75 volume, PA-76 screenshot, PA-74/77 Spotify."""
from __future__ import annotations


# ── PA-75 Volume ──────────────────────────────────────────────────────────────

def test_volume_self_test():
    from backend.skills.volume import self_test
    assert self_test()

def test_volume_set_regex():
    from backend.skills.volume import _SET_RE
    m = _SET_RE.search("set volume to 75")
    assert m and m.group(1) == "75"
    m2 = _SET_RE.search("volume to 50%")
    assert m2 and m2.group(1) == "50"

def test_volume_mute_regex():
    from backend.skills.volume import _MUTE_RE
    assert _MUTE_RE.search("mute") is not None
    assert _MUTE_RE.search("unmute please") is not None

def test_volume_up_regex():
    from backend.skills.volume import _UP_RE
    assert _UP_RE.search("volume up") is not None
    assert _UP_RE.search("louder") is not None

def test_volume_down_regex():
    from backend.skills.volume import _DOWN_RE
    assert _DOWN_RE.search("volume down") is not None
    assert _DOWN_RE.search("quieter") is not None

def test_volume_non_windows_returns_message():
    import platform
    if platform.system() != "Windows":
        from backend.skills.volume import run
        r = run({"utterance": "volume up"})
        assert "windows" in r.lower()

def test_volume_meta():
    from backend.skills.volume import META
    assert any("volume" in t for t in META["triggers"])
    assert any("mute" in t for t in META["triggers"])


# ── PA-76 Screenshot ──────────────────────────────────────────────────────────

def test_screenshot_self_test():
    from backend.skills.screenshot import self_test
    assert self_test()

def test_screenshot_meta():
    from backend.skills.screenshot import META
    assert any("screenshot" in t for t in META["triggers"])

def test_screenshot_desktop_path():
    from pathlib import Path
    from backend.skills.screenshot import _DESKTOP
    assert _DESKTOP == Path.home() / "Desktop"


# ── PA-74 + PA-77 Spotify ─────────────────────────────────────────────────────

def test_spotify_self_test():
    from backend.skills.spotify_control import self_test
    assert self_test()

def test_spotify_what_regex():
    from backend.skills.spotify_control import _WHAT_RE
    assert _WHAT_RE.search("what song is playing") is not None
    assert _WHAT_RE.search("what's playing") is not None
    assert _WHAT_RE.search("current song") is not None

def test_spotify_next_regex():
    from backend.skills.spotify_control import _NEXT_RE
    assert _NEXT_RE.search("next song") is not None
    assert _NEXT_RE.search("skip track") is not None

def test_spotify_pause_regex():
    from backend.skills.spotify_control import _PAUSE_RE
    assert _PAUSE_RE.search("pause music") is not None
    assert _PAUSE_RE.search("pause spotify") is not None

def test_spotify_play_regex():
    from backend.skills.spotify_control import _PLAY_RE
    assert _PLAY_RE.search("play music") is not None
    assert _PLAY_RE.search("resume") is not None

def test_spotify_not_configured_message():
    from backend.skills.spotify_control import run
    r = run({"utterance": "what song is playing"})
    # Without credentials, should return setup message
    assert "spotify" in r.lower()

def test_spotify_meta():
    from backend.skills.spotify_control import META
    assert any("song" in t for t in META["triggers"])
    assert any("pause" in t for t in META["triggers"])

def test_spotify_client_not_configured():
    from backend.core.spotify_client import is_configured
    # In test env without .env credentials, should return False
    import os
    if not os.getenv("SPOTIFY_CLIENT_ID"):
        assert is_configured() is False
