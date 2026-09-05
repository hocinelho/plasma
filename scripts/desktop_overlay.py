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
    PLASMA_OVERLAY_TRANSPARENCY
                            shape (default) | alpha | colorkey | none
    PLASMA_OVERLAY_SHAPE_ALPHA
                            1-254, default 96 — how opaque a pixel must be to
                             count as part of her in shape mode

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
# Shape mode: how opaque a pixel must be to be counted as part of her. 128 is
# the neutral place to cut — half coverage — now that the outline is sampled
# at the window's real pixel resolution rather than upscaled from a miniature.
# Raise it to cut further inside her (kills any rim of window background at
# the cost of shaving her edge); lower it to keep more of her soft edge.
DEFAULT_SHAPE_ALPHA = 128
# Ceiling on the sampling grid's width in device pixels. A 220px-wide overlay
# on a 125% display samples at 275 and never reaches this; it only stops a
# very large overlay from making each frame expensive.
SHAPE_MAX_WIDTH = 480
DEFAULT_TRANSPARENCY = "shape"
TRANSPARENCY_MODES = ("shape", "alpha", "colorkey", "none", "auto")
# How often the page re-reports her outline. She breathes and gestures, so the
# shape has to follow her; ~9 times a second is smooth to the eye and costs
# one downscaled 100px readback per update.
SHAPE_PERIOD_MS = 110


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


#  ══════════════════════════════════════════════════════════════════════
#  SHAPE — cut the window down to her silhouette
#  ══════════════════════════════════════════════════════════════════════
#  The two mechanisms above both try to make a *browser engine* composite
#  transparently, and both lose to the same thing: Chromium renders through
#  DirectComposition, so neither a colour key nor a DWM accent can reach its
#  pixels. That is the hard path, and it is not the one desktop mascots take.
#
#  Shimeji, Rainmeter skins, Windows' own splash screens: they all use a
#  *window region*. SetWindowRgn tells the OS "this window only exists inside
#  this outline" — everything else is not drawn, not composited and not even
#  clickable. It is applied by USER32/DWM around the content, so what renders
#  inside is irrelevant: WebView2 cannot composite past a hole that is not
#  there. No new dependency, no GPU trickery, a few hundred rectangles.
#
#  The trade-off is honest: a region has hard edges, so she looks like a
#  sticker cut-out rather than having softly-blended anti-aliased edges. That
#  is exactly how every desktop pet on Windows has ever looked.
#
#  The page reports her outline; this side turns it into the region. Reading
#  her alpha from the browser is possible at all because of the
#  preserveDrawingBuffer patch in vendor/talkinghead (added for /wallpaper).


def describe_outline(runs, canvas_w: int, canvas_h: int) -> str:
    """One line saying what the page actually reported.

    "She is still in a box" is the same sentence whether the region never
    applied, or applied perfectly to an outline that covers the whole window
    because the alpha channel came back opaque. Those need opposite fixes, so
    the console has to tell them apart without another round trip.

    A standing person fills roughly a fifth to a third of her own bounding
    box; anything near 100% means the alpha read is wrong, not that she is
    fat.
    """
    if not runs or canvas_w <= 0 or canvas_h <= 0:
        return "  outline: nothing reported"
    xs0 = [runs[i + 1] for i in range(0, len(runs) - 2, 3)]
    xs1 = [runs[i + 2] for i in range(0, len(runs) - 2, 3)]
    ys = [runs[i] for i in range(0, len(runs) - 2, 3)]
    covered = sum(b - a for a, b in zip(xs0, xs1))
    pct = 100.0 * covered / (canvas_w * canvas_h)
    line = (f"  outline: {len(ys)} runs, "
            f"x {min(xs0)}-{max(xs1)} y {min(ys)}-{max(ys) + 1} "
            f"of {canvas_w}x{canvas_h}, {pct:.0f}% of the window")
    if pct > 90:
        line += ("\n    ^ that is nearly the whole window, so the cut cannot "
                 "help: her canvas\n      is coming back opaque instead of "
                 "with an alpha channel.")
    return line


def runs_to_rects(
    runs, canvas_w: int, canvas_h: int, client_w: int, client_h: int,
    off_x: int = 0, off_y: int = 0,
) -> list[tuple[int, int, int, int]]:
    """Scanline runs from the page → rectangles in window coordinates.

    `runs` is flat — [y, x0, x1, y, x0, x1, ...] — because it crosses the
    JS↔Python bridge on every frame and a flat list of ints is a third the
    JSON of a list of triples. Each triple means "on row y, columns x0 up to
    (not including) x1 are her".

    The page samples on its own small grid (canvas_w × canvas_h) covering the
    whole viewport; the window's client area is whatever Windows says it is.
    Scaling between the two here rather than in the page is deliberate: this
    is the arithmetic that can be silently wrong — off by a scale factor and
    she is clipped to a sliver, off by an offset and she is clipped to
    nothing — so it lives in a pure function with tests.

    `off_x`/`off_y` shift client coordinates into window coordinates, since
    SetWindowRgn measures from the window's top-left, not the client's.
    """
    if canvas_w <= 0 or canvas_h <= 0 or client_w <= 0 or client_h <= 0:
        return []
    sx = client_w / canvas_w
    sy = client_h / canvas_h
    rects: list[tuple[int, int, int, int]] = []
    for i in range(0, len(runs) - 2, 3):
        y, x0, x1 = int(runs[i]), int(runs[i + 1]), int(runs[i + 2])
        if x1 <= x0:
            continue
        # Rounding both edges of a cell the same way makes neighbouring rows
        # and columns share an edge exactly, so the silhouette tiles with no
        # hairline gaps between the rectangles.
        left, right = round(x0 * sx), round(x1 * sx)
        top, bottom = round(y * sy), round((y + 1) * sy)
        left = max(0, min(left, client_w))
        right = max(0, min(right, client_w))
        top = max(0, min(top, client_h))
        bottom = max(0, min(bottom, client_h))
        if right <= left or bottom <= top:
            continue
        rects.append((left + off_x, top + off_y, right + off_x, bottom + off_y))
    return rects


def _set_window_region(hwnd: int, rects) -> bool:
    """Apply `rects` as the window's region, in one call.

    ExtCreateRegion takes the whole rectangle list at once. The obvious
    alternative — CreateRectRgn + CombineRgn per rectangle — is hundreds of
    GDI round trips several times a second, which is exactly the "heavy"
    this is supposed to avoid.

    On success Windows takes ownership of the region handle and it must not
    be deleted; on failure it is ours to free.
    """
    import ctypes
    from ctypes import wintypes

    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32

    class RGNDATAHEADER(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("iType", wintypes.DWORD),
            ("nCount", wintypes.DWORD),
            ("nRgnSize", wintypes.DWORD),
            ("rcBound", wintypes.RECT),
        ]

    RDH_RECTANGLES = 1
    n = len(rects)
    head_size = ctypes.sizeof(RGNDATAHEADER)
    rect_size = ctypes.sizeof(wintypes.RECT)
    buf = ctypes.create_string_buffer(head_size + n * rect_size)

    header = RGNDATAHEADER(
        head_size, RDH_RECTANGLES, n, n * rect_size,
        wintypes.RECT(min(r[0] for r in rects), min(r[1] for r in rects),
                      max(r[2] for r in rects), max(r[3] for r in rects)),
    )
    ctypes.memmove(buf, ctypes.byref(header), head_size)
    arr = (wintypes.RECT * n).from_buffer(buf, head_size)
    for i, (left, top, right, bottom) in enumerate(rects):
        arr[i].left, arr[i].top = left, top
        arr[i].right, arr[i].bottom = right, bottom

    gdi32.ExtCreateRegion.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    gdi32.ExtCreateRegion.restype = wintypes.HANDLE
    rgn = gdi32.ExtCreateRegion(None, len(buf), buf)
    if not rgn:
        return False

    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    if not user32.SetWindowRgn(hwnd, rgn, True):
        gdi32.DeleteObject(rgn)
        return False
    return True


def _apply_shape(title: str, runs, canvas_w: int, canvas_h: int) -> bool:
    """Clip the window to the outline the page just reported."""
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

    win, client, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT(0, 0)
    user32.GetWindowRect(hwnd, ctypes.byref(win))
    user32.GetClientRect(hwnd, ctypes.byref(client))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))

    rects = runs_to_rects(
        runs, canvas_w, canvas_h,
        client.right - client.left, client.bottom - client.top,
        origin.x - win.left, origin.y - win.top,
    )
    # An empty region would make the window vanish completely, with no way to
    # tell that from a crash. One bad frame — a paused render, a model swap
    # mid-load — must not be able to do that, so we simply keep the last shape.
    if not rects:
        return False
    return _set_window_region(hwnd, rects)


def _keep_out_of_the_taskbar(title: str) -> None:
    """WS_EX_TOOLWINDOW — she is scenery, not an app you Alt-Tab to."""
    if os.name != "nt":
        return
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return
    GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    get_long.restype = set_long.restype = ctypes.c_ssize_t
    set_long(hwnd, GWL_EXSTYLE, get_long(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW)


# The page half of shape mode. Injected only into the overlay window (it is
# guarded on window.pywebview existing, so it is inert in a normal browser).
#
# It samples her live WebGL canvas at the window's REAL pixel resolution and
# walks the alpha channel. The first version sampled a 100px-wide miniature to
# save work; scaled back up to a 220px window that is a 2.2x upscale, and the
# cut came out in visible 3px stair-steps — "the cutting of the border of the
# body is wrong, not professional", which it was. At native resolution the cut
# lands on the pixel the renderer actually drew, which is as clean as a region
# can be. It costs ~90k pixels read per frame instead of ~18k; that is about a
# millisecond, and it only runs when her outline has actually changed.
SHAPE_JS = r"""
(function () {
    if (window.__plasmaShape) return;
    window.__plasmaShape = true;

    var ALPHA = %(alpha)d;          // opacity above which a pixel counts as her
    var PERIOD = %(period)d;        // ms between outline updates
    // Device pixels, not CSS pixels: at 125%% scaling the window is physically
    // bigger than innerWidth says, and sampling in CSS pixels would put the
    // stair-steps straight back. Capped so a huge overlay cannot make each
    // frame expensive.
    var DPR = window.devicePixelRatio || 1;
    var W = Math.min(%(maxw)d, Math.max(32, Math.round(window.innerWidth * DPR)));
    var H = Math.max(8, Math.round(W * window.innerHeight / window.innerWidth));

    var probe = document.createElement('canvas');
    probe.width = W; probe.height = H;
    var pctx = probe.getContext('2d', { willReadFrequently: true });

    function source() {
        var holder = document.getElementById('avatar-human');
        var c = holder && holder.querySelector('canvas');
        return (c && c.width && c.height) ? c : null;
    }

    // Runs are reported in VIEWPORT space, not canvas space: her canvas need
    // not fill the window, and the Python side only knows about the window.
    // Drawing her into her real sub-rectangle of the probe makes the grid a
    // faithful miniature of what is on screen, whatever the layout does.
    function scan() {
        var src = source();
        if (!src) return null;
        var vw = document.documentElement.clientWidth  || window.innerWidth;
        var vh = document.documentElement.clientHeight || window.innerHeight;
        if (!vw || !vh) return null;
        var r = src.getBoundingClientRect();
        pctx.clearRect(0, 0, W, H);
        try {
            pctx.drawImage(src, r.left / vw * W, r.top / vh * H,
                                r.width / vw * W, r.height / vh * H);
        } catch (e) { return null; }
        var data;
        try { data = pctx.getImageData(0, 0, W, H).data; } catch (e) { return null; }

        var runs = [];
        for (var y = 0; y < H; y++) {
            var row = y * W * 4, x = 0;
            while (x < W) {
                while (x < W && data[row + x * 4 + 3] <= ALPHA) x++;
                if (x >= W) break;
                var x0 = x;
                while (x < W && data[row + x * 4 + 3] > ALPHA) x++;
                runs.push(y, x0, x);
            }
        }
        return runs.length ? runs : null;
    }

    // Chained rather than setInterval: if a frame takes longer than PERIOD we
    // wait for it instead of piling calls up on the bridge.
    //
    // An unchanged outline is not sent at all. She stands still and breathes,
    // so most frames are identical to the last one, and every call crosses a
    // JSON bridge and rebuilds a GDI region at the other end. Comparing the
    // runs first turns "always working" into "working only when she moves".
    var last = '';
    function tick() {
        var runs = null;
        try { runs = scan(); } catch (e) { runs = null; }
        var key = runs ? runs.join(',') : '';
        var done = (runs && key !== last)
            ? window.pywebview.api.set_shape(runs, W, H)
            : Promise.resolve();
        last = key;
        done.catch(function () {}).then(function () {
            setTimeout(tick, PERIOD);
        });
    }

    (function ready() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_shape) {
            return tick();
        }
        setTimeout(ready, 200);
    })();
})();
"""


def render_shape_js(alpha: int = DEFAULT_SHAPE_ALPHA) -> str:
    """SHAPE_JS with its placeholders filled in.

    One function rather than a dict at each call site: it is applied with `%`,
    so a placeholder added to the template and missed at a call site is a
    KeyError at runtime — inside the `loaded` handler, where it means no
    transparency and no obvious reason why.
    """
    return SHAPE_JS % {
        "alpha": alpha,
        "period": SHAPE_PERIOD_MS,
        "maxw": SHAPE_MAX_WIDTH,
    }


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

    # Where the mode came from matters as much as what it is. Debugging this
    # feature means setting PLASMA_OVERLAY_TRANSPARENCY in a shell, and a
    # PowerShell session keeps it for as long as the window is open — so a
    # setting from an hour ago silently beats the new default, the script
    # runs a mechanism nobody asked for any more, and it looks like the fix
    # did nothing. That happened. Say out loud when the environment is
    # steering, and say what it is overriding.
    forced = os.getenv("PLASMA_OVERLAY_TRANSPARENCY", "").strip().lower()
    # ...and an argument beats the environment, so there is always one command
    # that does what it says regardless of what the shell is remembering.
    for arg in sys.argv[1:]:
        if arg.startswith("--") and arg[2:].lower() in TRANSPARENCY_MODES:
            forced = arg[2:].lower()
    mode = forced or DEFAULT_TRANSPARENCY
    if mode == "auto":
        mode = "shape"          # what 'auto' used to mean, now that shape wins
    if mode not in TRANSPARENCY_MODES:
        print(f"  PLASMA_OVERLAY_TRANSPARENCY={mode!r} unknown — "
              f"using {DEFAULT_TRANSPARENCY!r}.")
        mode = DEFAULT_TRANSPARENCY
        forced = ""
    shape_alpha = _env_int("PLASMA_OVERLAY_SHAPE_ALPHA", DEFAULT_SHAPE_ALPHA)
    shape_alpha = max(1, min(254, shape_alpha))

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
    if forced and mode != DEFAULT_TRANSPARENCY:
        print(f"  Transparency mode: {mode}  <-- from PLASMA_OVERLAY_TRANSPARENCY "
              f"in this shell,\n     NOT the default ({DEFAULT_TRANSPARENCY}). "
              f"To go back to the default:")
        print("       Remove-Item Env:PLASMA_OVERLAY_TRANSPARENCY")
    else:
        print(f"  Transparency mode: {mode}")
    print("  Drag her to move her. Press Escape (with the window focused) to close.")
    print("  Plasma itself must already be running — python run_plasma.py")
    print(f"{bar}\n")

    class _Api:
        """Exposed to the page as window.pywebview.api.

        `close` backs the Escape handler injected below — a frameless window
        has no title bar, so there is otherwise no obvious way to close it.
        `set_shape` is the page reporting her outline; see SHAPE_JS.
        """

        # Said once, not nine times a second: a failing shape update is
        # already visible (she is in a box), and a per-frame log would bury
        # everything else the script prints.
        _shape_reported = False

        def close(self) -> None:
            window.destroy()

        def set_shape(self, runs, canvas_w: int, canvas_h: int) -> bool:
            ok = _apply_shape(WINDOW_TITLE, runs, canvas_w, canvas_h)
            if not _Api._shape_reported:
                _Api._shape_reported = True
                print("  Shape clipping: "
                      + ("on — the window is now her outline."
                         if ok else
                         "the page reported an outline but the window "
                         "region would not apply."))
                print(describe_outline(runs, canvas_w, canvas_h))
            return ok

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
        # transparent=True is the ONLY thing that stops WebView2 painting an
        # opaque background of its own. pywebview 6.2.1's edgechromium.py:
        #
        #     DefaultBackgroundColor = Color.FromArgb(255, r, g, b)   # opaque!
        #     if window.transparent: DefaultBackgroundColor = Transparent
        #
        # So without it the page's transparent pixels reveal a solid rectangle
        # of `background_color` — that filled box around her is not the window
        # frame, it is the browser itself. Every mode wants it gone: `alpha`
        # needs the real per-pixel alpha it switches on, `colorkey` needs the
        # form's key colour to actually be visible before it can be punched
        # out, and `shape` needs nothing painted inside the cut-out.
        # background_color must be plain 6-digit hex — pywebview validates
        # ^#(?:[0-9a-fA-F]{3}){1,2}$.
        transparent=(mode != "none"),
        background_color=chroma,
        js_api=_Api(),
    )

    def _wire_the_page() -> None:
        try:
            window.evaluate_js(
                "document.addEventListener('keydown', function(e) {"
                "  if (e.key === 'Escape') window.pywebview.api.close();"
                "});"
            )
        except Exception:
            pass   # cosmetic — closing the terminal still works
        if mode != "shape":
            return
        try:
            window.evaluate_js(render_shape_js(shape_alpha))
        except Exception as e:
            print(f"  Could not start the outline reporter: {e}")

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

            # Shape mode does its work from the page, once she has actually
            # rendered — there is no outline to cut to before then. All this
            # side has to do here is keep her out of the taskbar.
            if mode == "shape":
                _keep_out_of_the_taskbar(WINDOW_TITLE)
                print("  Shape mode: waiting for the page to report her outline.")
                print(_diagnose(WINDOW_TITLE))
                return

            # The two older mechanisms. Order follows how the window was
            # actually built: in 'colorkey' the window is opaque and painting
            # `chroma`, so the colour key is the one that can possibly work;
            # the DWM accent is a long shot afterwards, since it cannot show
            # through an opaque WebView2 on its own.
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
            if not applied:
                print("  If she is still boxed, the mode that does not depend "
                      "on the browser at all is:")
                print('    $env:PLASMA_OVERLAY_TRANSPARENCY = "shape"')

        threading.Thread(target=attempt, daemon=True).start()

    window.events.shown += _punch_out_the_background
    window.events.loaded += _wire_the_page
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
