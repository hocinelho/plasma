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

1. On the phone, open **`https://<ip>:8443/plasma.crt`** — the server hands
   the certificate straight to it. No copying files off the PC.

   (The file lives at `.plasma\certs\plasma.crt`, but it only exists after
   `serve_phone.py` has run once, and Windows hides dot-folders in Explorer —
   which is why it looks missing. Paste the path into the address bar, or use
   the URL above.)
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


## Stage mode — only the avatar

Tap **⛶ Full screen avatar** and everything except her disappears: she fills
the screen, stands on the bottom edge, and wanders slowly from side to side,
taking real steps as she moves. Tap her to talk; **✕** in the corner leaves.

It also asks the browser for true full screen, so even the address bar goes.
iOS Safari has no Fullscreen API — there the CSS still applies, and installing
Plasma to the home screen gives you the same result permanently.

**A limit worth stating:** a web page cannot draw over your phone's home
screen. No browser allows it, on iOS or Android — it is not a Plasma
limitation, and no setting unlocks it. A live overlay companion would have to
be a native Android app (a live wallpaper or an overlay service); iOS forbids
even that. Stage mode is the closest achievable *interactive* thing: she owns
the whole display while Plasma is open.

For her on the home screen itself, use the wallpaper studio below.


## Summoning her, like Siri

You can't have her floating over your icons, but you *can* have her arrive the
way Siri does: say a phrase, and she is there — full screen, already
listening, nothing to tap.

Open **`/?stage=1`** and that is exactly what happens. Add `&listen=0` if you
would rather she waited for a tap.

### "Hey Siri, Plasma"

On iPhone, Siri becomes her wake word:

1. **Shortcuts** app → **+** → *Add Action* → search **Open URLs**
2. Paste `https://<your-pc-ip>:8443/?stage=1`
3. Rename the shortcut to **Plasma** (tap the name at the top)
4. Done

Now *"Hey Siri, Plasma"* brings her up full screen and listening. The
shortcut name is the phrase, so call it whatever you want to say.

Two extras worth setting up while you're there:

- **Back Tap** — Settings → Accessibility → Touch → Back Tap → *Double Tap* →
  pick the Plasma shortcut. Two taps on the back of the phone summons her.
- **Action Button** (iPhone 15 Pro and later) — Settings → Action Button →
  *Shortcut* → Plasma.

On Android the same thing works from a home screen shortcut, and Google
Assistant routines can open the URL by voice.

### Why Siri and not "hey Plasma"

Her own wake word runs on the PC's microphone and needs Plasma to already be
open and in the foreground on the phone. A phone browser cannot bring itself
to the front — no web page can, on any platform. Siri can, so on the phone
Siri does the summoning and Plasma does everything after it.

Once she is up, "hey Plasma" and the clap work normally, and if you leave the
stage the wake word brings her back to it.


## Wallpaper studio — her on your home screen

Open **`/wallpaper`** (or tap *🖼 Make a wallpaper* on the main page) and you
get a picture of her sized to your exact screen, ready to set as the home
screen background. She stands behind your app icons rather than in front of
them — that difference is the browser limit above, and it is the only one.

| Control | What it does |
|---|---|
| Motion | plays any clip from `frontend/animations/` on a loop |
| Freeze | stops it dead, so you keep the frame you like |
| Expression | her face — neutral, happy, warm, thoughtful, serious |
| Size / left-right / up-down | where she stands and how much of the screen she takes |
| Mirror | flips her, for when she should face the other way |
| Background | transparent, a photo from your phone, or a solid colour |

Then **Make wallpaper**, long-press the result, and save it to Photos. On
iPhone: *Settings → Wallpaper → Add New Wallpaper → Photos*.

**Freeze is the point.** TalkingHead can hold a clip's first keyframe as a
static pose, but keyframe 0 of `waving` is arms-down — the wave hasn't
happened yet. Playing the motion and stopping it where you want gives you
every frame of all 21 clips to pick from instead of 21 opening frames.

A few details that matter:

- The export is rendered at your screen's true pixel size (e.g. 1179×2556 on
  an iPhone 14 Pro), not at the size of the preview, so it is sharp.
- **Transparent** background is usually what you want: it keeps your own
  wallpaper and simply adds her to it, so save it and set it over the top.
  Solid colour and photo backgrounds bake a background in.
- If she runs off an edge, the result screen says so. A cropped hand is the
  easiest mistake to make and the hardest to notice at thumbnail size.
- Leave the bottom-left of your home screen free of icons (iOS 18+ lets you
  place icons wherever you like) and she reads as standing among them rather
  than behind them.
