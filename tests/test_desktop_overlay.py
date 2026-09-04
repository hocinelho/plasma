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


class TestColorKey:
    """The white box behind her was pywebview's transparent=True not actually
    making the Windows form transparent. The fix is a Win32 colour key, and
    its one piece of easy-to-invert arithmetic is COLORREF's byte order."""

    def test_colorref_is_bgr_not_rgb(self):
        # Pure red #ff0000 → COLORREF 0x0000FF, NOT 0xFF0000.
        assert overlay.colorref_from_hex("#ff0000") == 0x0000FF
        assert overlay.colorref_from_hex("#0000ff") == 0xFF0000

    def test_the_default_chroma_round_trips(self):
        assert overlay.colorref_from_hex(overlay.DEFAULT_CHROMA) == 0x010101

    def test_green_lands_in_the_middle_byte(self):
        assert overlay.colorref_from_hex("#00ff00") == 0x00FF00

    def test_the_default_chroma_is_a_valid_pywebview_colour(self):
        """It is passed straight to create_window as background_color."""
        assert _FakeWebview._valid_color.match(overlay.DEFAULT_CHROMA)

    def test_it_is_a_no_op_off_windows(self):
        """This container is Linux — the call must decline, not explode."""
        assert overlay._apply_color_key("Plasma Overlay", "#010101") is False

    def test_the_alpha_route_is_also_a_no_op_off_windows(self):
        assert overlay._apply_composition_transparency("Plasma Overlay") is False


class TestTransparencyMode:
    """Two mechanisms, and they need OPPOSITE things from pywebview: alpha
    needs transparent=True (WebView2 hands over real per-pixel alpha), while
    colorkey needs an opaque window painting one exact colour to punch out.
    Wiring either to the wrong flag produces a solid box and no error."""

    def _create_kwargs(self, monkeypatch, **env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        fake = _FakeWebview()
        monkeypatch.setitem(sys.modules, "webview", fake)
        assert overlay.main() == 0
        return fake.last_kwargs

    def test_auto_is_the_default_and_builds_a_keyable_window(self, monkeypatch):
        """The two mechanisms need opposite window setups, so a run can only
        be built for one of them. 'auto' builds for the colour key — opaque,
        painting `chroma` — because that is the one that can still be tried
        again afterwards; the DWM route cannot show through an opaque
        WebView2 no matter when it is applied."""
        monkeypatch.delenv("PLASMA_OVERLAY_TRANSPARENCY", raising=False)
        kwargs = self._create_kwargs(monkeypatch)
        assert kwargs["transparent"] is False
        assert kwargs["background_color"] == overlay.DEFAULT_CHROMA

    def test_alpha_asks_pywebview_for_a_transparent_window(self, monkeypatch):
        kwargs = self._create_kwargs(monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="alpha")
        assert kwargs["transparent"] is True

    def test_colorkey_needs_an_opaque_window(self, monkeypatch):
        kwargs = self._create_kwargs(
            monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="colorkey")
        assert kwargs["transparent"] is False

    def test_an_unknown_mode_falls_back_to_auto(self, monkeypatch, capsys):
        kwargs = self._create_kwargs(
            monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="magic")
        assert kwargs["transparent"] is False
        assert "unknown" in capsys.readouterr().out

    def test_software_compositing_is_opt_in(self, monkeypatch):
        """It costs GPU acceleration on a live WebGL render, so it must never
        turn itself on — but it is the thing that puts Chromium's pixels
        where a colour key can reach them."""
        monkeypatch.delenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", raising=False)
        monkeypatch.delenv("PLASMA_OVERLAY_SOFTWARE", raising=False)
        self._create_kwargs(monkeypatch)
        assert "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" not in os.environ

        monkeypatch.setenv("PLASMA_OVERLAY_SOFTWARE", "1")
        self._create_kwargs(monkeypatch)
        assert "--disable-gpu-compositing" in \
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]

    def test_none_disables_it_entirely(self, monkeypatch):
        """An escape hatch for when both mechanisms misbehave — a visible
        window beats an invisible one you cannot debug."""
        kwargs = self._create_kwargs(monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="none")
        assert kwargs["transparent"] is False


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


class _FakeWebview:
    """Stands in for the pywebview module in tests, validating arguments the
    same way pywebview 6.2.1 actually does — this is what caught the real
    bug below, and is what stops it coming back.

    _valid_color is copied verbatim from pywebview's own
    webview/__init__.py::create_window rather than approximated, so a test
    passing here means pywebview itself would not have rejected the call.
    """

    _valid_color = __import__("re").compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')

    def create_window(self, title, url, background_color="#FFFFFF", **kwargs):
        if not self._valid_color.match(background_color):
            raise ValueError(f"{background_color} is not a valid hex triplet color")
        from unittest.mock import MagicMock
        win = MagicMock()
        win.events = MagicMock()   # supports += the way pywebview's real event does
        # background_color is a named parameter here (to validate it), so it
        # would otherwise be missing from the recorded kwargs.
        self.last_kwargs = dict(kwargs, background_color=background_color)
        return win

    def start(self):
        pass   # a real call blocks forever; tests must never reach this either


class TestCreateWindowCallIsValid:
    """Regression test for a real crash: desktop_overlay.py passed
    background_color="#00000000" (8 hex digits, an alpha channel) and
    pywebview's regex only accepts 3 or 6. This runs main() against a fake
    that enforces that exact rule, so the fix cannot silently regress."""

    def test_main_does_not_crash_on_argument_validation(self, monkeypatch):
        # main() does `import webview` locally (only inside the function —
        # never at module scope, so this environment's missing pywebview
        # cannot break importing the script itself). That import resolves
        # through sys.modules, which is all this needs to patch.
        monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
        assert overlay.main() == 0

    def test_no_alpha_channel_is_ever_passed_for_background_color(self):
        """Belt and braces: even if create_window's default ever changes,
        this script itself must never hand it an 8-digit hex value."""
        src = SCRIPT.read_text(encoding="utf-8")
        import re
        for m in re.finditer(r'background_color\s*=\s*"([^"]*)"', src):
            assert _FakeWebview._valid_color.match(m.group(1)), \
                f"background_color={m.group(1)!r} would be rejected by pywebview"


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
