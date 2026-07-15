# Plasma Avatar — Design

Plasma's avatar is the face of the assistant: the single element on screen
that makes it feel *present* and *alive* rather than a text box with a
microphone. This document describes what the avatar is, the contract it
exposes to the rest of the UI, and how it behaves in each state.

---

## Concept — "Plasma", a plasma-jelly companion

The avatar is a **creature / mascot companion**, not an abstract widget: a
soft, glowing blob of plasma-jelly with two big expressive eyes, a mouth
that speaks, and a little energy antenna. It is made of the same living
"plasma" light as the rest of the UI (bokeh motes, flowing streams), but
given a face and a personality so the user reads it as a companion who is
listening, thinking, and talking *with* them.

Design goals:

- **Alive first.** Eyes, blinking, gaze, breathing and squash-and-stretch
  do more for "alive" than raw detail. Personality over realism.
- **Legible state.** A glance should tell you whether Plasma is idle,
  listening, thinking, or speaking — by colour *and* by behaviour.
- **One material.** The creature is plasma/light, tying it to the living
  backdrop and the original orb. Colour shifts per mood.
- **Calm, not creepy.** Rounded, bottom-heavy body; friendly catchlights;
  gentle motion. Never uncanny.
- **Cheap and kind.** Pure 2D canvas, one `requestAnimationFrame` loop,
  and it honours `prefers-reduced-motion`.

---

## The contract

The avatar lives in **`frontend/avatar.js`** + **`frontend/avatar.css`**,
served at `/avatar.js` and `/avatar.css` (routes in `backend/main.py`).
It renders into `<canvas id="avatar">` and is driven entirely through three
globals — nothing else couples the UI to the avatar:

| Global | Type | Who writes it | Effect |
|---|---|---|---|
| `window.avatarState` | `'idle' \| 'listening' \| 'thinking' \| 'speaking'` | `setStatus()` in `index.html` | Selects the mood: colour, gaze, mouth, energy. |
| `window.avatarLevel` | `0..1` | the TTS lip-sync analyser | Live voice amplitude → mouth opening, body bounce, glow. Decays each frame; keep feeding it while speaking. |
| `window.avatarWakeBurst(ms=1700)` | function | wake-word / activation | A brief excited "waking up" reaction. |

`avatar.js` is loaded **before** the main inline script in `index.html`, so
it establishes these globals first; the rest of the page then reads and
writes them by bare name. Swapping or restyling the avatar means editing
only `avatar.js` / `avatar.css` — the contract stays put.

---

## States

| State | Colour | Eyes | Mouth | Energy |
|---|---|---|---|---|
| **idle** | calm blue | relaxed, occasional blink + slow look-around | content smile | slow breathe + bob, antenna at rest |
| **listening** | warm pink | wide, dilated, leaning toward you | soft anticipatory curve | antenna perks up, quicker breathing |
| **thinking** | teal/green | glance up, eyes roam (saccades) | small neutral line | thought-dots orbit the head, gentle wobble |
| **speaking** | cyan | happy, relaxed | opens with `avatarLevel` (lip-sync) | body bounces with the voice, antenna flicks |
| **waking** *(transient)* | bright gold | big and sparkling | open, surprised-delighted | scale pop, sparkle burst, antenna sparks |

`waking` is not a persistent state — it's the `avatarWakeBurst()` reaction
that briefly overrides whatever state is current, then eases back.

---

## How it moves

- **Breathing & bob** — a slow sine on the body radius (squash/stretch) and
  vertical position; rate and amplitude vary per state.
- **Gaze** — pupils track a smoothed target: a per-state resting direction
  plus periodic *saccades*. Thinking roams the most; listening locks on you.
- **Blink** — a quick close→open every few seconds (a half-sine on eye
  height), so the face never feels frozen.
- **Antenna** — a damped spring: it sways idly, flicks with the body's
  vertical velocity, jitters with the voice, and sparks on wake. Secondary
  motion is what sells "physical creature."
- **Lip-sync** — in `speaking`, the mouth is an ellipse whose height tracks
  `avatarLevel`; the body also bounces and the aura brightens with it.
- **Motes** — a few plasma glints orbit the body, some drawn behind and some
  in front for a cheap sense of depth.

`prefers-reduced-motion` damps all motion (~⅓), drops the mote/spark counts,
and keeps the face calm — the creature still reads as alive but stops moving
so much.

---

## Renderers

`avatar.js` ships three renderers behind the same contract, chosen with a
`data-avatar` attribute on the canvas (defaults to **human**):

- **`human`** *(default)* — a full-body, realistic 3D person built on the
  MIT-licensed [TalkingHead](https://github.com/met4citizen/TalkingHead)
  library (three.js). Facial expressions per mood, gaze/eye contact, hand
  gestures (waves on the wake word, sometimes raises a finger while
  thinking), and **real lip-sync**: the page hands Piper's TTS audio to
  `window.avatarSpeak(b64, text)`, word timings are estimated from the
  clip length, and TalkingHead converts words → visemes (English and
  German modules are bundled). Falls back to the mascot automatically if
  WebGL or module loading fails.
- **`mascot`** — Plasma, the plasma-jelly creature described above.
- **`orb`** — the original JARVIS neural-galaxy sphere: a perspective 3D
  node-sphere with a neural net, flowing fibre-optic ribbons, and bokeh
  depth orbs. Kept as an alternate look and a reference.

```html
<canvas id="avatar" data-avatar="mascot"></canvas>   <!-- opt into the creature -->
<canvas id="avatar" data-avatar="orb"></canvas>      <!-- opt into the sphere  -->
```

### Human renderer — assets & swapping the character

Everything is served locally (no CDN, works offline):

| Path | What |
|---|---|
| `frontend/vendor/talkinghead/` | TalkingHead modules + en/de lip-sync (MIT) |
| `frontend/vendor/three/` | three.js 0.180 + the addons TalkingHead needs (MIT) |
| `frontend/avatars/brunette.glb` | default character (from the TalkingHead repo, MIT) |

To use a different character, replace the GLB: any **Ready Player Me /
Avaturn**-style full-body GLB with ARKit/Oculus-viseme blend shapes and a
Mixamo-compatible rig works — drop it in `frontend/avatars/` and change the
URL in `avatar.js` (`showAvatar({ url: ... })`). Plain game models without
facial blend shapes (e.g. `girl_mechanic.glb`) load but can't emote or
lip-sync, so they're not suitable as-is.

The extra `window.avatarSpeak` hook is part of the contract now: optional,
only defined while the human renderer is active; `playBase64Audio()` in
`index.html` calls it first and falls back to plain `<audio>` playback (and
the amplitude-driven `avatarLevel` path) when it's absent.

---

## Roadmap

- Idle "personality" beats — rare yawns, look-arounds, reactions to long
  silences.
- Emotional range beyond the four states (happy / confused / error) once the
  backend can signal intent, not just pipeline phase.
- A tie-in to the JIRA "talking avatar" sprint: richer, phoneme-aware mouth
  shapes instead of a single amplitude-driven opening.
- Optional accent/theme colours so the creature can match a user's palette.
