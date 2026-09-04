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
import re
import sys
import threading

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


WINDOW_TITLE = "Plasma Overlay"
# Every pixel of EXACTLY this colour is punched out of the window by Windows.
# Near-black rather than the classic magenta because anti-aliased pixels along
# her silhouette get blended with it, and a faint dark fringe on a character
# with black hair and a navy outfit is invisible where a magenta one would
# not be. Nothing in the render is likely to land on exactly #010101.
DEFAULT_CHROMA = "#010101"


def colorref_from_hex(hex_color: str) -> int:
    """#rrggbb → Win32 COLORREF, which is 0x00BBGGRR — byte-reversed from the
    hex people actually write. Getting this backwards keys out a colour that
    is not on screen, so the window simply stays opaque with no error."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (b << 16) | (g << 8) | r


def _apply_color_key(title: str, hex_color: str) -> bool:
    """Make `hex_color` fully transparent — and click-through — on a window.

    pywebview's own transparent=True is not enough on Windows. It sets the
    WebView2 control's background to transparent, but never gives the WinForms
    window itself any transparency (no TransparencyKey, no AllowsTransparency,
    no layered style — checked against pywebview 6.2.1's winforms.py). So the
    page's transparent pixels reveal the *form's* opaque background instead of
    the desktop, which is the white box behind her.

    WS_EX_LAYERED + LWA_COLORKEY is the ancient, stable Win32 way to do it:
    Windows composites the window and drops every pixel matching the key.
    Those regions also stop receiving mouse input, so clicks land on whatever
    is behind her — which is what you want from something parked on top of
    your desktop all day.

    WS_EX_TOOLWINDOW additionally keeps her out of the taskbar and Alt-Tab.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TOOLWINDOW = 0x00000080
    LWA_COLORKEY = 0x00000001

    colorref = colorref_from_hex(hex_color)

    # SetWindowLongPtrW on 64-bit Windows; the 32-bit name is the fallback.
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    get_long.restype = ctypes.c_ssize_t
    set_long.restype = ctypes.c_ssize_t

    style = get_long(hwnd, GWL_EXSTYLE)
    set_long(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
    # Extended-style changes are not honoured until the frame is recalculated.
    # Without this the window keeps its old, unlayered behaviour and the key
    # below silently does nothing.
    SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x2, 0x1, 0x4, 0x20
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND, wintypes.COLORREF, ctypes.c_byte, wintypes.DWORD,
    ]
    return bool(user32.SetLayeredWindowAttributes(hwnd, colorref, 255, LWA_COLORKEY))


def _diagnose(title: str) -> str:
    """What Windows actually thinks about our window, in one block.

    Three rounds of guessing at which transparency mechanism works on a
    machine I cannot run anything on is two rounds too many. This reports the
    facts that decide it — whether the window was found at all, which styles
    stuck, and whether the APIs even exist here — so the next step is chosen
    from evidence rather than another guess.
    """
    if os.name != "nt":
        return "  (diagnostics are Windows-only)"
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    lines = [f"  window found      : {'yes, hwnd=' + str(hwnd) if hwnd else 'NO'}"]
    if not hwnd:
        lines.append("  -> nothing else can work until the window is findable")
        return "\n".join(lines)

    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    get_long.restype = ctypes.c_ssize_t
    ex = get_long(hwnd, -20)
    lines.append(f"  ex-style          : 0x{ex & 0xFFFFFFFF:08X}")
    lines.append(f"    WS_EX_LAYERED   : {'yes' if ex & 0x00080000 else 'no'}")
    lines.append(f"    WS_EX_TOOLWINDOW: {'yes' if ex & 0x00000080 else 'no'}")
    lines.append("  SetWindowCompositionAttribute: "
                 f"{'available' if hasattr(user32, 'SetWindowCompositionAttribute') else 'MISSING'}")
    try:
        dwm = ctypes.windll.dwmapi
        enabled = ctypes.c_int(0)
        dwm.DwmIsCompositionEnabled(ctypes.byref(enabled))
        lines.append(f"  DWM composition   : {'on' if enabled.value else 'OFF'}")
    except Exception as e:
        lines.append(f"  DWM composition   : unknown ({e})")
    return "\n".join(lines)


def _apply_composition_transparency(title: str) -> bool:
    """True per-pixel alpha, via the DWM composition attribute.

    The colour-key route above cannot see WebView2's output on many machines:
    Chromium renders through DirectComposition, and LWA_COLORKEY only applies
    to what the window itself paints. The window then just changes colour
    instead of disappearing — a dark box instead of a white one.

    This is the other mechanism: ask DWM to treat the window background as
    fully transparent, and let WebView2 hand it real alpha (which is what
    pywebview's transparent=True switches on). No colour key, so no fringing
    on her silhouette either.

    SetWindowCompositionAttribute is undocumented but stable since Windows 10
    and is what most transparent-window toolkits use.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    if not hasattr(user32, "SetWindowCompositionAttribute"):
        return False

    class ACCENTPOLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
        ]

    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.POINTER(ACCENTPOLICY)),
            ("SizeOfData", ctypes.c_size_t),
        ]

    ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
    WCA_ACCENT_POLICY = 19

    # GradientColor is 0xAABBGGRR — alpha 0 means "contribute nothing", i.e.
    # the window background is simply not painted.
    accent = ACCENTPOLICY(ACCENT_ENABLE_TRANSPARENTGRADIENT, 2, 0x00000000, 0)
    data = WINCOMPATTRDATA(WCA_ACCENT_POLICY, ctypes.pointer(accent),
                           ctypes.sizeof(accent))
    ok = bool(user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd),
                                                   ctypes.byref(data)))
    if ok:
        # Keep her off the taskbar and out of Alt-Tab, same as the other path.
        GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        get_long.restype = ctypes.c_ssize_t
        set_long.restype = ctypes.c_ssize_t
        set_long(hwnd, GWL_EXSTYLE, get_long(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW)
    return ok


def main() -> int:
    base = os.getenv("PLASMA_URL", "http://127.0.0.1:8000").rstrip("/")
    width = _env_int("PLASMA_OVERLAY_WIDTH", DEFAULT_WIDTH)
    height = _env_int("PLASMA_OVERLAY_HEIGHT", DEFAULT_HEIGHT)
    margin = _env_int("PLASMA_OVERLAY_MARGIN", DEFAULT_MARGIN)
    corner = os.getenv("PLASMA_OVERLAY_CORNER", DEFAULT_CORNER).strip().lower()
    watch = os.getenv("PLASMA_OVERLAY_WATCH", "1").strip() != "0"
    chroma = os.getenv("PLASMA_OVERLAY_CHROMA", DEFAULT_CHROMA).strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", chroma):
        print(f"  PLASMA_OVERLAY_CHROMA={chroma!r} is not a #rrggbb colour — "
              f"using {DEFAULT_CHROMA}.")
        chroma = DEFAULT_CHROMA

    mode = os.getenv("PLASMA_OVERLAY_TRANSPARENCY", "auto").strip().lower()
    if mode not in ("auto", "alpha", "colorkey", "none"):
        print(f"  PLASMA_OVERLAY_TRANSPARENCY={mode!r} unknown — using 'auto'.")
        mode = "auto"

    # Chromium normally composites through DirectComposition, which a colour
    # key cannot see — the window changes colour instead of disappearing.
    # Forcing software compositing puts its pixels back in the window's own
    # surface where LWA_COLORKEY reaches them. Costs GPU acceleration, and
    # she is a live WebGL render, so this is opt-in rather than the default.
    if os.getenv("PLASMA_OVERLAY_SOFTWARE", "").strip() == "1":
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
            + " --disable-gpu-compositing"
        ).strip()
        print("  Software compositing on (PLASMA_OVERLAY_SOFTWARE=1) — "
              "slower, but a colour key can reach her pixels.")

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
        WINDOW_TITLE,
        url,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        # "alpha" needs WebView2 to hand the window real per-pixel alpha,
        # which is exactly what pywebview's transparent=True switches on.
        # "colorkey" needs the opposite: an opaque window painting one exact
        # colour for _apply_color_key to punch out. background_color must be
        # plain 6-digit hex — pywebview validates ^#(?:[0-9a-fA-F]{3}){1,2}$.
        transparent=(mode == "alpha"),
        background_color=chroma,
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

    def _punch_out_the_background() -> None:
        """Make the window background disappear, once it actually exists.

        Retried briefly: `shown` can fire a beat before the HWND is findable
        by title, and a single miss would leave her in a solid box with no
        indication why. Says out loud what it did either way — the failure
        mode here is entirely visual, so a silent no-op is indistinguishable
        from the mechanism simply not working on this machine.
        """
        if mode == "none":
            return

        def attempt() -> None:
            import time
            # Wait for the HWND to exist; `shown` can fire a beat early.
            for _ in range(40):            # ~4 seconds
                if os.name != "nt":
                    return
                import ctypes
                if ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE):
                    break
                time.sleep(0.1)

            # Both mechanisms, in order, unless one was demanded explicitly.
            # Neither is reliable across every Windows build and GPU driver,
            # and asking the user to switch by hand costs a round trip each
            # time — so try, then report what actually took.
            # Order matters and follows how the window was actually built.
            # In 'auto'/'colorkey' the window is opaque and painting `chroma`,
            # so the colour key is the mechanism that can possibly work; the
            # DWM accent is applied afterwards only as a long shot, since it
            # cannot show through an opaque WebView2 on its own.
            applied = []
            if mode == "alpha":
                if _apply_composition_transparency(WINDOW_TITLE):
                    applied.append("alpha (DWM per-pixel)")
            else:
                if _apply_color_key(WINDOW_TITLE, chroma):
                    applied.append(f"colorkey {chroma}")
                if not applied and _apply_composition_transparency(WINDOW_TITLE):
                    applied.append("alpha (DWM per-pixel)")

            if applied:
                print(f"  Transparency applied: {', '.join(applied)}.")
            else:
                print("  Could not apply any transparency — she stays in a box.")
            print(_diagnose(WINDOW_TITLE))
            if not applied or mode == "auto":
                print("  If she is still boxed, paste the block above and try:")
                print('    $env:PLASMA_OVERLAY_SOFTWARE = "1"   '
                      '# software compositing, slower but keyable')

        threading.Thread(target=attempt, daemon=True).start()

    window.events.shown += _punch_out_the_background
    window.events.loaded += _wire_escape_to_close
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
