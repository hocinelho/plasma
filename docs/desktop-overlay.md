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

**PowerShell remembers `$env:` for the life of the window.** Something you
set an hour ago while debugging still wins over the defaults, and the script
just quietly does the old thing. It says so now — if the mode line reads
`<-- from PLASMA_OVERLAY_TRANSPARENCY in this shell`, that is what happened:

```powershell
Remove-Item Env:PLASMA_OVERLAY_TRANSPARENCY, Env:PLASMA_OVERLAY_CHROMA, Env:PLASMA_OVERLAY_SOFTWARE -ErrorAction SilentlyContinue
```

The mode can also be passed as an argument, which beats the environment — so
there is always one command that does what it says:

```powershell
python scripts\desktop_overlay.py --shape
```

## Transparency — the window *is* her outline

**Only her body shows. There is no window around her.** That is what `shape`
mode, the default, does — and it gets there by not trying to make the browser
transparent at all.

### Three backgrounds, not one

**The browser paints one.** pywebview 6.2.1's `edgechromium.py`:

```python
self.webview.DefaultBackgroundColor = Color.FromArgb(255, r, g, b)  # opaque!
if window.transparent:
    self.webview.DefaultBackgroundColor = Color.Transparent
```

Without `transparent=True` the WebView2 control fills itself with an **opaque**
`background_color`, and the page's transparent pixels reveal that. It is real
page content, so no amount of Win32 work on the window can remove it — the
window is doing what it was told. The overlay now passes `transparent=True`
in every mode for exactly this reason.

**The form paints the second**, and it is the one that survives fixing the
first. Same file, a few lines further down:

```python
if window.transparent and self.browser:
    self.SetStyle(SupportsTransparentBackColor, True)
    self.browser.DefaultBackgroundColor = Color.Transparent
else:
    self.BackColor = ColorTranslator.FromHtml(window.background_color)
```

`BackColor` is set only in the `else`. Turning transparency on therefore
leaves the form at the WinForms default, `SystemColors.Control` — #F0F0F0,
near-white. Two symptoms, one cause: her anti-aliased edge blends into it, so
she gets a white outline; and the window region trails the render by one
update, so a moving hand uncovers it for a moment. The overlay repaints it the
key colour and then punches that colour out. Unlike WebView2's content this
background *is* painted through GDI into the window's own surface, which is
where `LWA_COLORKEY` can reach — an opaque WebView2 covering it up is the
reason the colour key looked useless on its own.

**The window paints the third**, and this is the one that is genuinely hard.
pywebview never gives the WinForms window any transparency — no
`TransparencyKey`, no `AllowsTransparency`, no layered style (checked against
its `winforms.py`) — and helping it from Win32 does not work either, because
both ways fail for the *same* reason. Chromium renders through
**DirectComposition**; its pixels never pass through the window's own surface,
so neither a colour key (`WS_EX_LAYERED` + `LWA_COLORKEY`) nor a DWM accent
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

It works like this, up to ~9 times a second (and not at all while she holds
still, since an unchanged outline is not re-sent):

1. The page draws her live WebGL canvas into a 2D canvas at the window's
   **device-pixel** resolution — `innerWidth × devicePixelRatio`, so a 125%
   display samples at 275px, not 220.
2. It walks the alpha channel and emits one run per horizontal stretch of
   "this is her" — a few hundred integers.
3. `scripts/desktop_overlay.py` scales those runs into window coordinates and
   hands them to `ExtCreateRegion` + `SetWindowRgn` in **one** GDI call.

Sampling at native resolution is the difference between a clean cut and a
ragged one. The first version sampled a 100px-wide miniature to save work;
scaled back up to a 220px window that is a 2.2× upscale, and the outline came
out in visible three-pixel stair-steps.

No new dependency — `ctypes` and a little JavaScript. Reading her alpha at all
is possible because of the `preserveDrawingBuffer` patch in
`frontend/vendor/talkinghead/` (added for the wallpaper studio).

Two things follow from it, both good:

- **Clicks outside her go straight through** to whatever is behind. A region
  clips mouse input as well as pixels, so this comes for free.
- **Dragging her means grabbing her body**, since that is the only part of
  the window that exists.

And two trade-offs, stated plainly.

**Hard edges.** A region is a cut, not a blend — she looks like a sticker
cut-out rather than having softly anti-aliased edges. That is how every
desktop pet on Windows has ever looked, and it is the price of not needing a
full per-pixel-alpha compositor to get her out of the box.

**The outline lags the render.** She animates at 60fps and the outline is
re-cut at ~22Hz, so a fast gesture can briefly show a pixel or two of window
background where her hand used to be. Keying that background out is what
keeps it from being *visible* lag. Fixing it properly means owning her pixels
rather than clipping around them — `UpdateLayeredWindow`, which is what a
native floating avatar (a Messenger chat head, a Siri orb) gets from its
platform's compositor for free. That means rendering her offscreen, shipping
every frame out of the browser, painting it into a bare layered window, and
re-implementing click and drag by hand, since there would no longer be a
browser under the cursor to receive them. Worth it if the cut-out ever stops
being good enough; not before.

`PLASMA_OVERLAY_SHAPE_ALPHA` (default 190) is where the cut falls. Sampled at
native resolution the alpha value *is* the pixel's coverage, and the default
sits well past halfway on purpose: a pixel at 50% coverage is half her and
half window background, and a region cannot show only its half of her — so
including it draws a rim of background colour around her. Cutting at 190
shaves a sub-pixel sliver off her silhouette, which nobody notices, and
removes the halo, which everybody does. Lower it if she looks eaten into.

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
whether the shape actually applied. Read the **mode** line first:

- *"Transparency mode: colorkey"* (or `alpha`, or `none`) — shape mode never
  ran. A `$env:PLASMA_OVERLAY_TRANSPARENCY` left over in this PowerShell
  window is overriding it; see above.
- *"Shape clipping: on"* — the region applied. The `outline:` line under it
  says what was cut: how many runs, the bounding box, and what fraction of
  the window she covers. A standing person covers roughly a fifth to a third;
  if it says 90-100%, the cut is working and cannot help, because her canvas
  is coming back opaque rather than with an alpha channel. The script says so
  in as many words.
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
