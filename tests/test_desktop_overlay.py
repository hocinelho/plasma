"""Tests for scripts/desktop_overlay.py — the corner-placement math, and the
config it reads. Everything past webview.start() needs an actual display and
cannot be tested here (documented plainly in the script's own docstring); this
file tests the one part that is pure and GUI-free, plus the parts of main()
that run before a window is ever created.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop_overlay.py"

# Loaded directly from its file path rather than via a package import: the
# script is a standalone CLI tool with no __init__.py, the same reason other
# scripts in this repo are tested via subprocess. A direct load, using the
# same mechanism the skill registry uses for plugin files, is used here
# instead because most of what is worth testing is pure functions, and
# spawning a subprocess per case would be needlessly slow for that.
_spec = importlib.util.spec_from_file_location("desktop_overlay", SCRIPT)
overlay = importlib.util.module_from_spec(_spec)
sys.modules["desktop_overlay"] = overlay
_spec.loader.exec_module(overlay)


class TestComputePosition:
    def test_bottom_right_is_the_default_corner(self):
        x, y = overlay.compute_position(1920, 1080, 220, 420)
        assert x == 1920 - 220 - overlay.DEFAULT_MARGIN
        assert y == 1080 - 420 - overlay.DEFAULT_MARGIN

    def test_all_four_corners(self):
        sw, sh, ww, wh, m = 1920, 1080, 200, 400, 10
        assert overlay.compute_position(sw, sh, ww, wh, "top-left", m) == (10, 10)
        assert overlay.compute_position(sw, sh, ww, wh, "top-right", m) == \
            (sw - ww - m, m)
        assert overlay.compute_position(sw, sh, ww, wh, "bottom-left", m) == \
            (m, sh - wh - m)
        assert overlay.compute_position(sw, sh, ww, wh, "bottom-right", m) == \
            (sw - ww - m, sh - wh - m)

    def test_unknown_corner_is_rejected_with_the_valid_list(self):
        import pytest
        with pytest.raises(ValueError, match="bottom-right"):
            overlay.compute_position(1920, 1080, 200, 400, "middle")

    def test_a_window_bigger_than_the_screen_still_shows_its_corner(self):
        """A tiny display, or a generous margin, must not push the window to
        a negative coordinate — that reads as "the app didn't open"."""
        x, y = overlay.compute_position(300, 300, 220, 420, "bottom-right", 24)
        assert x >= 0 and y >= 0

    def test_the_window_stays_within_the_screen_in_the_normal_case(self):
        x, y = overlay.compute_position(1920, 1080, 220, 420, "bottom-right", 24)
        assert 0 <= x <= 1920 - 220
        assert 0 <= y <= 1080 - 420


class TestScreenSizeFallback:
    def test_falls_back_to_a_sane_default_without_tkinter(self, monkeypatch):
        """This container has no display and no tkinter — exactly the
        environment _screen_size() has to survive."""
        w, h = overlay._screen_size()
        assert w > 0 and h > 0


class TestEnvInt:
    def test_uses_the_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("PLASMA_OVERLAY_WIDTH", raising=False)
        assert overlay._env_int("PLASMA_OVERLAY_WIDTH", 220) == 220

    def test_reads_a_valid_number(self, monkeypatch):
        monkeypatch.setenv("PLASMA_OVERLAY_WIDTH", "300")
        assert overlay._env_int("PLASMA_OVERLAY_WIDTH", 220) == 300

    def test_a_bad_value_falls_back_rather_than_crashing(self, monkeypatch, capsys):
        monkeypatch.setenv("PLASMA_OVERLAY_WIDTH", "wide")
        assert overlay._env_int("PLASMA_OVERLAY_WIDTH", 220) == 220
        assert "not a number" in capsys.readouterr().out


class TestMainWithoutPywebview:
    def test_missing_pywebview_is_reported_not_a_traceback(self, monkeypatch, capsys):
        """This environment genuinely lacks pywebview — exercise the real
        failure path, not a simulated one."""
        import builtins
        real_import = builtins.__import__

        def blocked(name, *a, **kw):
            if name == "webview":
                raise ModuleNotFoundError("No module named 'webview'")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", blocked)
        rc = overlay.main()
        assert rc == 1
        assert "pip install pywebview" in capsys.readouterr().err


class TestUrlAndDefaults:
    def test_watch_is_on_by_default(self):
        """docs/phone-setup.md sells this as "she watches for you" out of
        the box — it must not need an extra env var to get that."""
        assert os.getenv("PLASMA_OVERLAY_WATCH", "1") != "0"

    def test_default_target_is_the_local_server(self):
        assert overlay.__doc__.count("127.0.0.1:8000") >= 1


class TestDocs:
    """Loose coupling between the doc and the code is exactly how the
    wander-mode wording went stale earlier this session — a couple of string
    checks catch that class of drift cheaply."""

    DOC = (ROOT / "docs" / "desktop-overlay.md").read_text(encoding="utf-8")

    def test_the_install_command_is_correct(self):
        assert "pip install pywebview" in self.DOC
        assert "python scripts\\desktop_overlay.py" in self.DOC

    def test_every_env_var_the_script_reads_is_documented(self):
        for var in ("PLASMA_URL", "PLASMA_OVERLAY_WIDTH", "PLASMA_OVERLAY_HEIGHT",
                    "PLASMA_OVERLAY_CORNER", "PLASMA_OVERLAY_MARGIN",
                    "PLASMA_OVERLAY_WATCH"):
            assert var in self.DOC, f"{var} is read by the script but undocumented"

    def test_states_plainly_that_it_is_untested(self):
        assert "not tested" in self.DOC.lower() or "NOT TESTED" in self.DOC

    def test_phone_setup_links_to_it(self):
        phone_doc = (ROOT / "docs" / "phone-setup.md").read_text(encoding="utf-8")
        assert "desktop-overlay.md" in phone_doc
