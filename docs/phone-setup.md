# Plasma on your phone

The phone runs the **interface** — microphone, the 3D avatar, the chat. The
PC keeps doing the heavy work (Whisper, the LLM, Piper). Everything stays on
your own network.

## Start the phone server

```powershell
python serve_phone.py
```

It prints an address like `https://192.168.1.42:8443`. Open that on the phone
(same Wi-Fi) and accept the certificate warning once.

**HTTPS is not optional.** Phones refuse microphone access on plain `http://`
LAN addresses, which is the whole reason this launcher exists.

## Install it to the home screen

**Android (Chrome):** menu → *Add to Home screen* / *Install app*. It gets the
Plasma icon and opens without browser chrome.

**iPhone (Safari):** Share button → *Add to Home Screen*. Must be **Safari** —
Chrome on iOS cannot install web apps.

Once installed it behaves like an app: own icon, no address bar, full screen,
and it respects the notch and home indicator.

### The catch on iPhone

iOS is stricter than Android about self-signed certificates. Accepting the
warning in Safari is usually enough to browse, but iOS may still refuse
microphone access, because `getUserMedia` demands a *trusted* certificate,
not merely an accepted one.

If the mic is blocked, install the certificate properly:

1. Copy `.plasma/certs/plasma.crt` from the PC to the phone (AirDrop, email
   to yourself, or open `https://<ip>:8443/` and download it).
2. iPhone: **Settings → Profile Downloaded → Install**.
3. Then **Settings → General → About → Certificate Trust Settings** and
   switch Plasma's certificate **on**. This second step is the one people
   miss — without it the certificate is installed but not trusted.

Android generally works after simply accepting the warning.

## Character size

The avatar panel is sized against the viewport (`52dvh`, capped at 470 px),
not fixed pixels, so she fills a sensible share of any screen. `dvh` rather
than `vh` means the collapsing address bar doesn't crop her legs.

The camera framing adapts to the space available:

| Panel height | Framing |
|---|---|
| ≥ 330 px | full body |
| 260–330 px | mid (waist up) |
| < 260 px | upper body |

A full-body figure in a 250 px panel is too small to read, so she is framed
closer instead. Rotating the phone re-frames automatically. Override with
`<canvas id="avatar" data-avatar-view="full">` if you always want one framing.

## Battery and heat

The 3D avatar is a real-time WebGL render and will warm the phone during long
sessions. If that becomes annoying, switch the phone to the light renderer:

```html
<canvas id="avatar" data-avatar="mascot">
```

The mascot is 2D canvas and costs a fraction of the power.
