#!/usr/bin/env python3
"""
Plasma desktop overlay — she stands in the corner of your screen, on top of
every other window, while you work.

    python scripts/desktop_overlay.py

Loads the same transparent /?overlay=1 page the Android companion uses (see
android/README.md), in a small always-on-top window instead of a phone's
floating one. Windows-focused (that is what a "laptop, free moving, front of
all apps" ask means in practice), but nothing here is Windows-only code —
pywebview supports Linux (GTK/QT) and macOS (Cocoa) too, on whatever their
own transparency story allows.

Requires:
    pip install pywebview
Windows also needs the WebView2 Runtime, which ships built into Windows 10
and 11 already (it is the same engine behind modern Edge) — nothing to
install for the vast majority of machines. If yours is missing it, pywebview
will say so; get it from Microsoft's WebView2 download page.

Environment variables (all optional):
    PLASMA_URL              default http://127.0.0.1:8000
    PLASMA_OVERLAY_WIDTH    default 220
    PLASMA_OVERLAY_HEIGHT   default 420
    PLASMA_OVERLAY_CORNER   bottom-right (default) | bottom-left |
                             top-right | top-left
    PLASMA_OVERLAY_MARGIN   pixels from the screen edge, default 24
    PLASMA_OVERLAY_WATCH    "1" (default) or "0" — camera reactions on/off,
                             see docs/phone-setup.md "Camera reactions"

Plasma itself must already be running (`python run_plasma.py`) — this window
is only the display, exactly like the Android app; the thinking still
happens in the normal backend process.

NOT TESTED ON AN ACTUAL WINDOWS MACHINE. Written against pywebview's
documented API; there is no Windows box, and no display at all, available to
run it on here. The corner-placement math below IS tested (it needs no GUI),
everything past webview.start() is not. Treat the first run as the real
test and report back what pywebview actually does.
"""
from __future__ import annotations

import os
import sys

DEFAULT_WIDTH = 220
DEFAULT_HEIGHT = 420
DEFAULT_MARGIN = 24
DEFAULT_CORNER = "bottom-right"
CORNERS = ("bottom-right", "bottom-left", "top-right", "top-left")


def compute_position(
    screen_w: int, screen_h: int, win_w: int, win_h: int,
    corner: str = DEFAULT_CORNER, margin: int = DEFAULT_MARGIN,
) -> tuple[int, int]:
    """Top-left (x, y) so the window sits in the given screen corner.

    Pure and GUI-free on purpose: this is the one part of the script that is
    actually worth being wrong about silently (a window placed off-screen
    looks like the app crashed), so it is the one part with tests.
    """
    if corner not in CORNERS:
        raise ValueError(f"Unknown corner {corner!r}. Choose from: {', '.join(CORNERS)}")
    x = margin if "left" in corner else screen_w - win_w - margin
    y = margin if "top" in corner else screen_h - win_h - margin
    # A window bigger than the screen (tiny display, generous margin) must
    # still show its top-left corner rather than being dragged fully
    # off-screen in the other direction.
    return max(0, x), max(0, y)


def _screen_size() -> tuple[int, int]:
    """Best-effort screen resolution, without requiring pywebview to already
    be importable — tkinter ships with the standard python.org Windows
    installer, so this works even before we know whether webview does."""
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 1920, 1080   # a reasonable modern default if we truly cannot tell


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"  {name}={raw!r} is not a number — using {default}.")
        return default


def main() -> int:
    base = os.getenv("PLASMA_URL", "http://127.0.0.1:8000").rstrip("/")
    width = _env_int("PLASMA_OVERLAY_WIDTH", DEFAULT_WIDTH)
    height = _env_int("PLASMA_OVERLAY_HEIGHT", DEFAULT_HEIGHT)
    margin = _env_int("PLASMA_OVERLAY_MARGIN", DEFAULT_MARGIN)
    corner = os.getenv("PLASMA_OVERLAY_CORNER", DEFAULT_CORNER).strip().lower()
    watch = os.getenv("PLASMA_OVERLAY_WATCH", "1").strip() != "0"

    try:
        import webview
    except ImportError:
        print(
            "\n  pywebview is not installed.\n\n"
            "      pip install pywebview\n\n"
            "  On Windows this also needs the WebView2 Runtime, which ships "
            "built into\n  Windows 10/11 already — nothing further to do on "
            "almost any machine.\n",
            file=sys.stderr,
        )
        return 1

    screen_w, screen_h = _screen_size()
    try:
        x, y = compute_position(screen_w, screen_h, width, height, corner, margin)
    except ValueError as e:
        print(f"  {e}", file=sys.stderr)
        return 1

    query = "overlay=1"
    if watch:
        query += "&watch=1"
    url = f"{base}/?{query}"

    bar = "-" * 60
    print(f"\n{bar}")
    print(f"  Plasma desktop overlay — {url}")
    print(f"  {width}x{height} in the {corner} corner ({screen_w}x{screen_h} screen)")
    print("  Drag her to move her. Press Escape (with the window focused) to close.")
    print("  Plasma itself must already be running — python run_plasma.py")
    print(f"{bar}\n")

    class _Api:
        """Exposed to the page as window.pywebview.api — see the Escape
        handler injected below. A window has no title bar in frameless mode,
        so there is otherwise no obvious way to close it."""

        def close(self) -> None:
            window.destroy()

    window = webview.create_window(
        "Plasma",
        url,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
        background_color="#00000000",
        js_api=_Api(),
    )

    def _wire_escape_to_close() -> None:
        try:
            window.evaluate_js(
                "document.addEventListener('keydown', function(e) {"
                "  if (e.key === 'Escape') window.pywebview.api.close();"
                "});"
            )
        except Exception:
            pass   # cosmetic — closing the terminal still works

    window.events.loaded += _wire_escape_to_close
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
