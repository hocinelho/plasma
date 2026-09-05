# Desktop overlay (Windows) — she stands in the corner of your screen

The Android app puts her over your phone's home screen. This is the same
idea for a laptop: a small always-on-top window, transparent everywhere
except her, sitting in a corner while you work in every other app.

```powershell
python run_plasma.py        # she still runs here — this is only the window
pip install pywebview
python scripts\desktop_overlay.py
```

Only her body appears — the window is clipped to her outline, so there is no
box and clicks outside her land on whatever is behind. She appears
bottom-right, ~220×420px, on top of everything, watching the
camera for a raised hand by default (see
[Camera reactions](phone-setup.md#camera-reactions--raise-a-hand-she-waves-back)).
Drag her to move her. Press **Escape** with the window focused to close her.

## What this is

The same trick as the Android app: no second implementation of the avatar,
just a window. [pywebview](https://pywebview.flowrl.com/) opens one, points
it at `http://127.0.0.1:8000/?overlay=1` — the exact page the phone
companion loads — and Plasma's own server does everything else: the 3D, the
lip-sync, the LLM, the memory. `scripts/desktop_overlay.py` is under 200
lines and almost all of it is figuring out where the window should sit.

Unlike the phone, there is no certificate to deal with. The overlay talks to
`127.0.0.1`, which browsers (and WebView2, the engine behind it) treat as a
secure context regardless of HTTP vs HTTPS, so the microphone works without
the self-signed-cert dance `serve_phone.py` needs for a real network address.

## Configuring it

Environment variables, all optional:

| Variable | Default | |
|---|---|---|
| `PLASMA_URL` | `http://127.0.0.1:8000` | point it at another machine's Plasma if you're not running it locally |
| `PLASMA_OVERLAY_WIDTH`, `PLASMA_OVERLAY_HEIGHT` | `220`, `420` | her size on screen |
| `PLASMA_OVERLAY_CORNER` | `bottom-right` | or `bottom-left`, `top-right`, `top-left` |
| `PLASMA_OVERLAY_MARGIN` | `24` | pixels from the screen edge |
| `PLASMA_OVERLAY_WATCH` | `1` (on) | set `0` to skip the camera prompt entirely |
| `PLASMA_OVERLAY_TRANSPARENCY` | `shape` | or `alpha`, `colorkey`, `none` — see below |
| `PLASMA_OVERLAY_SHAPE_ALPHA` | `96` | 1-254 — how opaque a pixel must be to count as her, `shape` mode only |
| `PLASMA_OVERLAY_SOFTWARE` | off | `1` forces software compositing so a colour key can reach her pixels |
| `PLASMA_OVERLAY_CHROMA` | `#010101` | the colour punched out in `colorkey` mode only |

```powershell
$env:PLASMA_OVERLAY_CORNER = "top-left"
$env:PLASMA_OVERLAY_WATCH = "0"
python scripts\desktop_overlay.py
```

## Transparency — the window *is* her outline

**Only her body shows. There is no window around her.** That is what `shape`
mode, the default, does — and it gets there by not trying to make the browser
transparent at all.

### Why the obvious approach does not work

pywebview's `transparent=True` alone is **not enough on Windows**. It makes
the WebView2 *control* transparent but never gives the WinForms *window* any
transparency — no `TransparencyKey`, no `AllowsTransparency`, no layered
style (checked against pywebview 6.2.1's `winforms.py`). The page's
transparent pixels then reveal the form's own opaque background: the white
box.

Helping it from Win32 does not fix it either, and both ways of doing so fail
for the *same* reason. Chromium renders through **DirectComposition** — its
pixels never pass through the window's own surface — so neither a colour key
(`WS_EX_LAYERED` + `LWA_COLORKEY`) nor a DWM accent
(`SetWindowCompositionAttribute`) can reach them. You get a box that changes
colour instead of a box that goes away. Forcing `--disable-gpu-compositing`
puts the pixels back where a key can see them, at the cost of the GPU on a
live WebGL render, and still does not work everywhere.

### What `shape` does instead

Stop fighting the renderer. Cut the window down to her outline with a
**window region** (`SetWindowRgn`) — the same technique behind Shimeji-style
desktop pets, Rainmeter skins and Windows' own splash screens. A region tells
the OS "this window only exists inside this outline". Everything else is not
drawn, not composited, and not clickable. It is applied by USER32/DWM
*around* the content, so what renders inside is irrelevant: WebView2 cannot
composite past a hole that is not there.

It works like this, ~9 times a second:

1. The page downscales her live WebGL canvas into a ~100px-wide 2D canvas
   (the GPU does the resize inside `drawImage`, so this is cheap).
2. It walks the alpha channel and emits one run per horizontal stretch of
   "this is her" — a few hundred integers.
3. `scripts/desktop_overlay.py` scales those runs into window coordinates and
   hands them to `ExtCreateRegion` + `SetWindowRgn` in **one** GDI call.

No new dependency — `ctypes` and a little JavaScript. Reading her alpha at all
is possible because of the `preserveDrawingBuffer` patch in
`frontend/vendor/talkinghead/` (added for the wallpaper studio).

Two things follow from it, both good:

- **Clicks outside her go straight through** to whatever is behind. A region
  clips mouse input as well as pixels, so this comes for free.
- **Dragging her means grabbing her body**, since that is the only part of
  the window that exists.

And one trade-off, stated plainly: a region has **hard edges**. She looks
like a sticker cut-out rather than having softly blended anti-aliased edges.
That is how every desktop pet on Windows has ever looked, and it is the price
of not needing a full per-pixel-alpha compositor (what Electron ships) to get
her out of the box.

`PLASMA_OVERLAY_SHAPE_ALPHA` (default 96) is where the cut falls. It is
biased high on purpose — better a hair *inside* her outline than a rim of
window background around her. Lower it if she looks eaten into; raise it if
you see a dark halo.

### The other modes

`alpha` and `colorkey` are the two browser-side attempts described above,
kept because they need no per-frame work and do produce soft edges on the
machines where they happen to work. `colorkey` pairs with
`PLASMA_OVERLAY_CHROMA` (near-black rather than the classic magenta, so that
edge blending is invisible on a character with dark hair) and with
`PLASMA_OVERLAY_SOFTWARE=1`. `auto` is accepted and means `shape`.

`PLASMA_OVERLAY_TRANSPARENCY=none` turns the whole thing off — a visible
window beats an invisible one you cannot debug.

### If she is still in a box

The script prints the mode, then a diagnostic block, then one line saying
whether the shape actually applied. Read that line first:

- *"Shape clipping: on"* — the region applied. If you still see a box, it is
  not this window.
- *"the page reported an outline but the window region would not apply"* —
  Win32 refused; paste the diagnostic block.
- **Nothing at all about shape clipping** — the page never reported an
  outline. That means the 3D renderer fell back to the flat mascot (check the
  browser console at `http://127.0.0.1:8000/?overlay=1`), since only the
  full-body avatar has a silhouette to read.

## Known limits

- **Hard edges.** See the trade-off above.
- **She is a window, not a wallpaper.** She floats above your apps; she cannot
  be painted *between* your desktop icons and the wallpaper. For that, use the
  wallpaper studio at `/wallpaper`.
- **Dragging vs. tapping.** `easy_drag` (pywebview's frameless-window drag)
  and "tap her to talk" share the same click. A plain click still reaches
  the page as a click; only an actual drag moves the window. There is no
  touch-slop tuning available here the way the Android app has, so this is
  a coarser approximation of the same idea. In `shape` mode both only work
  on her body — the rest of the window is not there to click.
- **No system tray icon.** Closing her is Escape (window focused) or closing
  the terminal that launched the script. pywebview does not give a frameless
  window a built-in close affordance, and building a tray icon was more
  machinery than this warranted for a first version.
- **Battery/CPU.** Same cost as the phone's live WebGL render — hide her
  (Escape) when you're not using her, or set `PLASMA_OVERLAY_WATCH=0` if the
  camera on top of that is more than you want running.

## Not tested on an actual Windows machine

This was written against pywebview's documented API in an environment with
no display and no Windows box to run it on. The corner-placement math
(`compute_position` in the script) needs no GUI and **is** tested — see
`tests/test_desktop_overlay.py`. Everything from `webview.start()` onward —
the transparency actually rendering correctly, `easy_drag` behaving as
described, WebView2 being present — is not verified. Treat the first run as
the real test, and report back exactly what happens if it doesn't look
right; from the description of a real failure this is generally a small fix.
