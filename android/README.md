# Plasma Companion (Android)

Your avatar, floating on top of the home screen and every other app. Drag her
to move her, tap her to talk.

This is the one platform where the thing you probably wanted is actually
possible. iOS has no overlay API for any app, native or not. Android does:
`SYSTEM_ALERT_WINDOW`, the same permission behind Messenger's chat heads.

## What this app is

A window, and nothing else. It holds one transparent `WebView` pointed at
`https://<your-pc>:8443/?overlay=1` — the page Plasma already serves. All the
3D, the lip-sync, the animations, the memory and the LLM stay exactly where
they are. The app contributes three things the web cannot do for itself:

1. a window that sits above other apps,
2. a foreground service so she survives you switching apps,
3. the microphone while she is not the focused app.

About 400 lines of Kotlin. There is no second avatar implementation to keep
in step, which is the whole reason it is built this way.

## Building it

You need **Android Studio** (Ladybug or newer) and a phone with USB debugging
on. There is no prebuilt APK in this repo and no wrapper JAR — Android Studio
supplies Gradle itself.

1. Android Studio → *Open* → select this `android/` folder
2. Let it sync (it downloads the Android Gradle Plugin the first time)
3. Plug in the phone → *Run*

From the command line, with `ANDROID_HOME` set and a wrapper generated once
via `gradle wrapper`:

```bash
./gradlew assembleDebug
# app/build/outputs/apk/debug/app-debug.apk
```

## Using it

1. Start Plasma on the PC with `python serve_phone.py` and note the
   `https://<ip>:8443` address it prints.
2. Open the app, type that address in.
3. Tap **Allow display over other apps** → switch Plasma on in the Settings
   screen Android opens → come back.
4. Tap **Allow microphone**.
5. Tap **Show Plasma**. The app steps out of the way and she appears.

She stays until you tap **Hide**, or **Hide** in her notification.

Set her height with the slider before showing her; tap **Show Plasma** again
to apply a new size.

## The certificate

Plasma signs its own certificate, so Android will not trust it — correctly,
since nothing tells Android the machine is yours.

Blanket-accepting every certificate error is the usual shortcut and it is a
bad one: the app would then trust *anything* answering on that address, which
on a shared or public network is exactly the attack the warning exists to
prevent. Instead the first certificate seen for your address is remembered by
SHA-256 fingerprint, and only that certificate is accepted afterwards. If it
ever changes, the load stops and says so.

Regenerated your certificate (`python serve_phone.py --force-cert`, or moved
to a new network)? Tap **Forget saved certificate** and the next connection
pins the new one.

## Known limits

- **She is a window, not a widget.** She floats above the home screen; she
  cannot be placed *between* your icons and the wallpaper. For that, use the
  wallpaper studio at `/wallpaper` instead — the two work well together.
- **The wake word still runs on the PC.** "Hey Plasma" is detected by the PC's
  microphone. The phone's microphone is used for what you say to her after
  tapping. Tapping her is the phone's wake word.
- **Battery.** A live WebGL render in an always-on window is not free. Hide her
  when you are not using her; the notification's *Hide* is one tap.
- **Android 14+** requires the microphone permission before she can be shown at
  all, because the service declares a microphone foreground type. The app says
  so rather than crashing.
- **Not tested on a device by the author of this code.** It is written against
  the documented APIs but has never been run — treat the first launch as the
  real test, and expect to fix something.
