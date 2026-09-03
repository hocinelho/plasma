# Desktop overlay (Windows) — she stands in the corner of your screen

The Android app puts her over your phone's home screen. This is the same
idea for a laptop: a small always-on-top window, transparent everywhere
except her, sitting in a corner while you work in every other app.

```powershell
python run_plasma.py        # she still runs here — this is only the window
pip install pywebview
python scripts\desktop_overlay.py
```

She appears bottom-right, ~220×420px, on top of everything, watching the
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
| `PLASMA_OVERLAY_CHROMA` | `#010101` | the colour punched out to make the window see-through — see below |

```powershell
$env:PLASMA_OVERLAY_CORNER = "top-left"
$env:PLASMA_OVERLAY_WATCH = "0"
python scripts\desktop_overlay.py
```

## How the transparency works, and how to fix it if it looks wrong

pywebview's own `transparent=True` is **not enough on Windows**, which is why
the first version showed her in a white box. It makes the WebView2 *control*
transparent but never gives the WinForms *window* any transparency — no
`TransparencyKey`, no `AllowsTransparency`, no layered style (checked against
pywebview 6.2.1's `winforms.py`). So the page's transparent pixels revealed
the form's own opaque background instead of your desktop.

Instead the window is told to paint one exact colour (`PLASMA_OVERLAY_CHROMA`,
default `#010101`), and Windows is asked to drop every pixel of that colour
via `WS_EX_LAYERED` + `LWA_COLORKEY`. Those regions become fully see-through
**and click-through**, so clicks around her land on whatever is behind.

The default is near-black rather than the classic magenta because
anti-aliased pixels along her silhouette get blended with the key colour. A
faint dark fringe on a character with black hair and a navy outfit is
invisible; a magenta one would not be.

**If parts of her go transparent**, some pixel in the render matched the key
exactly. Pick a colour that does not occur in her:

```powershell
$env:PLASMA_OVERLAY_CHROMA = "#010203"
python scripts\desktop_overlay.py
```

**If the box is still solid**, the colour key never got applied — the script
prints a line saying so. That means the window could not be found by title,
which would be worth reporting.

## Known limits

- **Anti-aliased edges pick up a faint fringe** of the key colour. That is
  inherent to colour-key transparency; only a full per-pixel-alpha compositor
  (what Electron does) avoids it, which is a much larger dependency than this
  warrants.
- **She is a window, not a wallpaper.** She floats above your apps; she cannot
  be painted *between* your desktop icons and the wallpaper. For that, use the
  wallpaper studio at `/wallpaper`.
- **Dragging vs. tapping.** `easy_drag` (pywebview's frameless-window drag)
  and "tap her to talk" share the same click. A plain click still reaches
  the page as a click; only an actual drag moves the window. There is no
  touch-slop tuning available here the way the Android app has, so this is
  a coarser approximation of the same idea.
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
