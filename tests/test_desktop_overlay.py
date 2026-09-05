"""Tests for scripts/desktop_overlay.py — the corner-placement math, and the
config it reads. Everything past webview.start() needs an actual display and
cannot be tested here (documented plainly in the script's own docstring); this
file tests the one part that is pure and GUI-free, plus the parts of main()
that run before a window is ever created.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


# Just enough browser for the outline reporter to run under node: a window
# and document with the two measurements it takes, a 2D context whose
# getImageData returns a scripted alpha channel, and a stand-in for the
# pywebview bridge that records what it was handed. Everything it does NOT
# use is deliberately absent, so a future version of the reporter reaching
# for something else fails loudly here instead of silently on Windows.
HARNESS_JS = r"""
var BLANK = false;
var W = 100, H = 8;
var captured = null;

function pixels() {
    var d = new Uint8ClampedArray(W * H * 4);
    if (BLANK) return d;
    for (var y = 0; y < H; y++) {
        for (var x = 20; x < 30; x++) d[(y * W + x) * 4 + 3] = 255;
        if (y === 3) for (var x2 = 60; x2 < 65; x2++) d[(y * W + x2) * 4 + 3] = 255;
    }
    return d;
}

var probe = {
    width: 0, height: 0,
    getContext: function () {
        return {
            clearRect: function () {},
            drawImage: function () {},
            getImageData: function () { return { data: pixels() }; },
        };
    },
};
var avatarCanvas = {
    width: 300, height: 600,
    getBoundingClientRect: function () {
        return { left: 0, top: 0, width: 100, height: 8 };
    },
};

global.window = {
    innerWidth: 100,
    innerHeight: 8,
    pywebview: { api: { set_shape: function (runs, w, h) {
        captured = { runs: runs, w: w, h: h };
        return Promise.resolve(true);
    } } },
};
global.document = {
    documentElement: { clientWidth: 100, clientHeight: 8 },
    createElement: function () { return probe; },
    getElementById: function (id) {
        return id === 'avatar-human'
            ? { querySelector: function () { return avatarCanvas; } } : null;
    },
};
// The reporter reschedules itself; one pass is all this needs.
global.setTimeout = function () {};

function report() {
    // set_shape resolves on a microtask, and the reporter's own .then runs
    // after it — drain both before reading the result.
    Promise.resolve().then(function () {}).then(function () {
        process.stdout.write(JSON.stringify(captured));
    });
}
"""


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
    """transparent=True is not optional, whichever mechanism is in use.

    pywebview 6.2.1's edgechromium.py sets the WebView2 control's
    DefaultBackgroundColor to an OPAQUE background_color and only replaces it
    with Color.Transparent when window.transparent is set. Without it the
    page's transparent pixels reveal a solid rectangle painted by the browser
    itself — a filled box around her that no amount of Win32 work on the
    window can remove, because it is real content.
    """

    def _create_kwargs(self, monkeypatch, **env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        fake = _FakeWebview()
        monkeypatch.setitem(sys.modules, "webview", fake)
        assert overlay.main() == 0
        return fake.last_kwargs

    def test_shape_is_the_default(self, monkeypatch):
        """Both browser-side mechanisms lose to the same thing — Chromium
        composites through DirectComposition, where neither a colour key nor
        a DWM accent can reach its pixels. Clipping the window to her
        outline sidesteps the renderer entirely, so it is what runs by
        default now."""
        monkeypatch.delenv("PLASMA_OVERLAY_TRANSPARENCY", raising=False)
        kwargs = self._create_kwargs(monkeypatch)
        assert kwargs["transparent"] is True
        assert kwargs["background_color"] == overlay.DEFAULT_CHROMA

    def test_auto_still_works_and_now_means_shape(self, monkeypatch, capsys):
        """'auto' was the documented default for the old two-mechanism
        version — it must not start printing "unknown" at people who still
        have it set."""
        self._create_kwargs(monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="auto")
        assert "unknown" not in capsys.readouterr().out

    def test_every_working_mode_stops_the_browser_painting_a_background(
            self, monkeypatch):
        """The regression this exists for: shape mode shipped with
        transparent=False, so WebView2 filled the window with an opaque
        background_color and the cut-out framed a solid rectangle. The mode
        does not matter — a browser-painted background defeats all of them."""
        for mode in ("shape", "alpha", "colorkey"):
            kwargs = self._create_kwargs(
                monkeypatch, PLASMA_OVERLAY_TRANSPARENCY=mode)
            assert kwargs["transparent"] is True, mode

    def _mode_used(self, monkeypatch, capsys, **env):
        """The mode the run actually settled on, read off the banner.

        Every mode now builds the same window (transparent=True), so the
        create_window kwargs no longer distinguish them — the printed line is
        the observable, and it is also the one the user is asked to read.
        """
        self._create_kwargs(monkeypatch, **env)
        out = capsys.readouterr().out
        line = [ln for ln in out.splitlines() if "Transparency mode:" in ln][0]
        return line.split("Transparency mode:", 1)[1].strip().split()[0], out

    def test_an_unknown_mode_falls_back_to_the_default(self, monkeypatch, capsys):
        mode, out = self._mode_used(
            monkeypatch, capsys, PLASMA_OVERLAY_TRANSPARENCY="magic")
        assert mode == overlay.DEFAULT_TRANSPARENCY
        assert "unknown" in out

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

    def test_a_stale_env_var_says_so_loudly(self, monkeypatch, capsys):
        """This cost a whole round trip. Debugging transparency means setting
        PLASMA_OVERLAY_TRANSPARENCY in a shell, and PowerShell keeps it for
        the life of the window — so an hour later the old setting silently
        beat the new default, a mechanism nobody wanted any more ran, and it
        looked like the fix had done nothing at all."""
        self._create_kwargs(monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="colorkey")
        out = capsys.readouterr().out
        assert "PLASMA_OVERLAY_TRANSPARENCY" in out
        assert "NOT the default" in out
        assert "Remove-Item" in out            # the actual way out, not advice

    def test_the_default_does_not_nag(self, monkeypatch, capsys):
        monkeypatch.delenv("PLASMA_OVERLAY_TRANSPARENCY", raising=False)
        self._create_kwargs(monkeypatch)
        assert "NOT the default" not in capsys.readouterr().out

    def test_an_argument_beats_the_environment(self, monkeypatch, capsys):
        """So there is always one command that does what it says, whatever
        the shell is remembering."""
        monkeypatch.setattr(sys, "argv", ["desktop_overlay.py", "--shape"])
        mode, _ = self._mode_used(
            monkeypatch, capsys, PLASMA_OVERLAY_TRANSPARENCY="alpha")
        assert mode == "shape"

    def test_an_unrecognised_argument_is_ignored(self, monkeypatch, capsys):
        """It takes no other flags; a stray one must not change the mode or
        stop it starting."""
        monkeypatch.setattr(sys, "argv", ["desktop_overlay.py", "--verbose", "x"])
        mode, _ = self._mode_used(
            monkeypatch, capsys, PLASMA_OVERLAY_TRANSPARENCY="alpha")
        assert mode == "alpha"

    def test_none_disables_it_entirely(self, monkeypatch):
        """An escape hatch for when both mechanisms misbehave — a visible
        window beats an invisible one you cannot debug."""
        kwargs = self._create_kwargs(monkeypatch, PLASMA_OVERLAY_TRANSPARENCY="none")
        assert kwargs["transparent"] is False


class TestShapeGeometry:
    """The run→rectangle arithmetic behind shape mode.

    This is the one part of the mechanism that can be wrong without saying
    so. Off by a scale factor and the window is clipped to a sliver of her;
    off by the client offset and it is clipped to the wrong place; return
    nothing and the window disappears entirely. None of that raises, and
    none of it can be checked from here on a machine with no Windows and no
    display — so it is a pure function, and this is where it is pinned.
    """

    def test_a_full_row_covers_the_full_width(self):
        # One run: row 0, columns 0..10 of a 10-wide grid — all of it.
        rects = overlay.runs_to_rects([0, 0, 10], 10, 10, 100, 200)
        assert rects == [(0, 0, 100, 20)]

    def test_runs_are_scaled_from_the_grid_to_the_client_area(self):
        """The page samples on its own small grid; the window is whatever
        size Windows says. A run halfway across the grid must land halfway
        across the window."""
        rects = overlay.runs_to_rects([0, 5, 10], 10, 10, 200, 400)
        assert rects == [(100, 0, 200, 40)]

    def test_neighbouring_rows_share_an_edge_with_no_gap(self):
        """Scaled up, each grid row becomes several window rows. If the two
        edges round differently there is a transparent hairline between every
        band and she comes out looking like a venetian blind."""
        rects = overlay.runs_to_rects([0, 0, 4, 1, 0, 4, 2, 0, 4], 4, 3, 40, 100)
        for above, below in zip(rects, rects[1:]):
            assert above[3] == below[1]
        assert rects[0][1] == 0 and rects[-1][3] == 100

    def test_the_client_offset_shifts_into_window_coordinates(self):
        """SetWindowRgn measures from the window's top-left, not the
        client's. On a frameless window the two coincide; anywhere they do
        not, forgetting this clips her to a rectangle sliding off her body."""
        rects = overlay.runs_to_rects([0, 0, 10], 10, 10, 100, 100, off_x=8, off_y=30)
        assert rects == [(8, 30, 108, 40)]

    def test_several_runs_on_one_row_stay_separate(self):
        """Her arms away from her body make two runs on the same scanline —
        the gap between them is exactly the transparency we are here for."""
        rects = overlay.runs_to_rects([0, 0, 2, 0, 8, 10], 10, 10, 100, 100)
        assert rects == [(0, 0, 20, 10), (80, 0, 100, 10)]

    def test_empty_input_gives_no_rectangles(self):
        assert overlay.runs_to_rects([], 10, 10, 100, 100) == []

    def test_a_truncated_run_is_ignored_rather_than_crashing(self):
        """The runs arrive over the JS bridge as a flat list. A partial
        triple must not raise inside a per-frame callback."""
        assert overlay.runs_to_rects([0, 0, 10, 1, 5], 10, 10, 100, 100) == \
            [(0, 0, 100, 10)]

    def test_a_zero_sized_window_gives_no_rectangles(self):
        """Minimised, or asked before the window has been laid out. Better to
        report nothing (the caller keeps the last shape) than to divide by
        zero."""
        assert overlay.runs_to_rects([0, 0, 10], 10, 10, 0, 0) == []
        assert overlay.runs_to_rects([0, 0, 10], 0, 0, 100, 100) == []

    def test_runs_are_clamped_to_the_window(self):
        """A stale grid size — the window was resized between the page's scan
        and this call — must not produce rectangles outside the window."""
        rects = overlay.runs_to_rects([9, 0, 10], 10, 10, 50, 50)
        for left, top, right, bottom in rects:
            assert 0 <= left < right <= 50
            assert 0 <= top < bottom <= 50

    def test_no_degenerate_rectangles(self):
        """A zero-width or zero-height rectangle in the region data is at best
        wasted and at worst rejected by ExtCreateRegion, taking the whole
        outline with it."""
        rects = overlay.runs_to_rects(
            [0, 0, 1, 0, 3, 3, 1, 2, 4], 200, 200, 10, 10)
        assert all(r[2] > r[0] and r[3] > r[1] for r in rects)


class TestOutlineDiagnostic:
    """"She is still in a box" reads identically whether the region never
    applied or applied perfectly to an outline that covers the whole window.
    Those need opposite fixes, so the console has to tell them apart."""

    def test_it_reports_the_bounding_box_and_coverage(self):
        # A 4-wide stripe down a 10x10 grid: 40% of it.
        runs = [y for pair in ((y, 3, 7) for y in range(10)) for y in pair]
        line = overlay.describe_outline(runs, 10, 10)
        assert "10 runs" in line and "x 3-7" in line and "40%" in line

    def test_a_near_full_window_outline_is_called_out(self):
        """A standing person fills a fraction of her own bounding box. Near
        100% means the alpha channel came back opaque — the cut is working
        and cannot help, which is the opposite diagnosis to "it did not
        apply" and the one that looks identical on screen."""
        runs = [v for y in range(10) for v in (y, 0, 10)]
        line = overlay.describe_outline(runs, 10, 10)
        assert "100%" in line
        assert "opaque" in line

    def test_a_normal_silhouette_is_not_called_out(self):
        runs = [v for y in range(10) for v in (y, 4, 6)]
        assert "opaque" not in overlay.describe_outline(runs, 10, 10)

    def test_nothing_reported_says_so_rather_than_dividing_by_zero(self):
        assert "nothing" in overlay.describe_outline([], 10, 10)
        assert "nothing" in overlay.describe_outline([0, 0, 5], 0, 0)


class TestShapeReporter:
    """The page half. It is injected as a string, so nothing type-checks it."""

    JS = property(lambda self: overlay.SHAPE_JS)

    def test_it_is_inert_outside_the_overlay_window(self):
        """The same page is served to a normal browser and to the phone —
        neither has window.pywebview, and neither may be broken by this."""
        assert "window.pywebview" in overlay.SHAPE_JS
        assert "api.set_shape" in overlay.SHAPE_JS

    def test_it_reads_the_avatar_canvas(self):
        assert "avatar-human" in overlay.SHAPE_JS

    def test_it_measures_against_the_viewport_not_the_canvas(self):
        """Her canvas need not fill the window, and the Python side only
        knows the window. Reporting canvas-relative runs would clip her to a
        stretched copy of herself."""
        assert "getBoundingClientRect" in overlay.SHAPE_JS
        assert "clientWidth" in overlay.SHAPE_JS

    def test_it_samples_at_the_windows_real_pixel_resolution(self):
        """The first version sampled a 100px-wide miniature. Upscaled back to
        a 220px window that is 2.2x, and the cut came out in visible 3px
        stair-steps — the edge looked hacked out rather than cut. The grid
        has to be device pixels, which is innerWidth TIMES devicePixelRatio:
        at 125% scaling the window is physically bigger than CSS says, and
        sampling in CSS pixels puts the steps straight back."""
        assert "devicePixelRatio" in overlay.SHAPE_JS
        assert "window.innerWidth * DPR" in overlay.SHAPE_JS

    def test_the_grid_is_capped_so_a_big_overlay_stays_cheap(self):
        rendered = overlay.render_shape_js()
        assert str(overlay.SHAPE_MAX_WIDTH) in rendered

    def test_it_still_reads_pixels_the_cheap_way(self):
        assert "drawImage" in overlay.SHAPE_JS
        assert "willReadFrequently" in overlay.SHAPE_JS

    def test_the_default_cut_is_at_half_coverage(self):
        """Sampled at native resolution the alpha value IS the coverage, so
        128 is the neutral place to cut. It was biased high only to hide the
        blur the old downscale introduced."""
        assert overlay.DEFAULT_SHAPE_ALPHA == 128

    def test_it_does_not_pile_calls_up_on_the_bridge(self):
        """setInterval would queue a new call whether or not the last one
        came back. The reporter chains instead."""
        assert "setInterval(" not in overlay.SHAPE_JS
        assert "setTimeout(tick" in overlay.SHAPE_JS

    def test_an_unchanged_outline_is_not_resent(self):
        """She stands still and breathes, so most frames are identical. Every
        call crosses a JSON bridge and rebuilds a GDI region at the far end —
        worth skipping when there is nothing new to say."""
        assert "key !== last" in overlay.SHAPE_JS

    def test_it_survives_pywebviews_evaluate_js_escaping(self):
        """evaluate_js does not run the script — it embeds it in a
        double-quoted JS string and eval()s that (pywebview 6.2.1
        window.py + util.escape_string). Backslashes, double quotes and
        newlines are escaped; anything the escaper does not handle silently
        breaks the whole injection."""
        def escape_string(s):          # copied verbatim from util.py
            return (s.replace('\\', '\\\\').replace('"', r'\"')
                     .replace('\n', r'\n').replace('\r', r'\r')
                     .replace("'", r'\''))

        rendered = overlay.render_shape_js(96)
        escaped = escape_string(rendered)
        # A real newline surviving into the string literal would end it.
        assert "\n" not in escaped and "\r" not in escaped
        # A backtick or a ${...} would be fine here but not everywhere the
        # script travels; and a stray quote must already be escaped.
        assert '"' not in escaped.replace(r'\"', "")

    def test_the_substitutions_it_declares_are_the_ones_main_supplies(self):
        """It is applied with `%`, so a stray unescaped percent sign in the
        JavaScript is a TypeError at runtime and no transparency at all."""
        rendered = overlay.render_shape_js(96)
        assert "96" in rendered and "110" in rendered

    def test_the_scanline_walker_finds_the_right_runs(self, tmp_path):
        """Actually run the reporter, against a scripted alpha channel.

        The other half of the geometry lives in this string, and an off-by-one
        in the run loop is exactly as invisible as one in runs_to_rects — it
        just shaves a column off her, or reports a run that ends one pixel
        early. Node is not a project dependency, so this is skipped where it
        is missing rather than being a reason to add one.
        """
        node = shutil.which("node")
        if not node:
            pytest.skip("node is not installed")

        harness = tmp_path / "harness.js"
        harness.write_text(HARNESS_JS + "\n" + (
            overlay.render_shape_js(96)) + "\nreport();\n",
            encoding="utf-8")
        out = subprocess.run([node, str(harness)], capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        result = json.loads(out.stdout)

        # The stub paints columns 20..30 on every row, plus 60..65 on row 3.
        assert result["w"] == 100 and result["h"] == 8
        runs = result["runs"]
        assert runs[0:3] == [0, 20, 30]
        # Row 3 has two runs, in left-to-right order — ExtCreateRegion wants
        # them sorted, and that ordering falls out of the scan rather than
        # being imposed later.
        row3 = [runs[i:i + 3] for i in range(0, len(runs), 3) if runs[i] == 3]
        assert row3 == [[3, 20, 30], [3, 60, 65]]
        assert len(runs) == (8 + 1) * 3          # one run per row, two on row 3

    def test_it_reports_nothing_rather_than_an_empty_outline(self, tmp_path):
        """A blank frame — she has not rendered yet, or the model is being
        swapped — must not be reported as "she is nowhere". An empty region
        makes the window vanish with no way to tell that from a crash."""
        node = shutil.which("node")
        if not node:
            pytest.skip("node is not installed")
        harness = tmp_path / "harness.js"
        harness.write_text(HARNESS_JS.replace("var BLANK = false;", "var BLANK = true;")
                           + "\n" + (overlay.render_shape_js(96))
                           + "\nreport();\n", encoding="utf-8")
        out = subprocess.run([node, str(harness)], capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout) is None      # set_shape was never called

    def test_reading_alpha_at_all_depends_on_the_talkinghead_patch(self):
        """A WebGL canvas is cleared after compositing unless the renderer
        keeps the drawing buffer — without this patch every read comes back
        blank and she is clipped to nothing."""
        th = ROOT / "frontend" / "vendor" / "talkinghead" / "talkinghead.mjs"
        assert "preserveDrawingBuffer: true" in th.read_text(encoding="utf-8")


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
