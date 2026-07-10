# Session Log — 2026-06-25

> What we built today on branch `claude/enhance-plasma-project-cOZli`.
> Vision suite: object locate fix, face/gesture/expression perception,
> face identity, and proactive reactions.

---

## 1. moondream "find my X" empty-response fix

**Problem:** `ollama moondream` kept returning empty strings for "find my keys",
so the locate skill reported nothing.

**Root cause:** moondream is flaky on *question-form* prompts but reliable at
*describing* an image.

**Fix (two strategies, `backend/skills/locate.py`):**
1. Ask the native question `"Where is the {obj}?"` — retry 3×.
2. If still empty, ask it to **describe the whole scene**, then search that
   description in Python for the object and return the relevant sentence.

Also expanded `_NOT_FOUND_WORDS` with moondream phrasings ("not visible in",
"there is no", "doesn't appear", …).

Commits: `09d8725`, `b6dca4c`, `7d779d3`.
Confirmed working — "Where is my keys?" → "The keys are on the table, near the bottle."

---

## 2. Face / hand / expression perception (MediaPipe)

**Picked MediaPipe (35.8k ⭐, Apache 2.0)** over big vision-LLMs (GLM-4V / Kimi-VL):
real-time landmark tracking at ~30 fps on CPU. Big VLMs give a paragraph per
frame (1–5 s) and would freeze the machine — wrong tool for tracking.

**New files:**
- `backend/modules/vision/perception.py` — pure, testable functions:
  - `count_fingers()` (0–5), `classify_gesture()` (victory ✌️, thumbs up 👍,
    open palm, fist, pointing)
  - `classify_expression()` from FaceLandmarker blendshapes
    (happy 😀 / sleepy 😴 / winking 😉 / neutral)
  - `summarize()` → natural-language description (EN + DE)
  - `Perceiver` class + `get_perceiver()` singleton
- `backend/skills/vision_query.py` — voice skill: "how many fingers?",
  "how do I look?", "do you see me?", "remember my face as …"

Commit: `4a90469`. Tested: victory sign, finger count, smile/sleepy all read correctly.

---

## 3. Face identity recognition (DeepFace)

**DeepFace (23k ⭐, MIT)** — optional dep (like resemblyzer for voice).
Faces stored in `.plasma/faces/<name>/*.jpg`.

- `backend/modules/vision/face_id.py` — `parse_enroll_command()`, `enroll()`,
  `identify()`, `list_people()`.
- Voice: "remember my face as Hocine" enrolls; "do you recognize my face?" identifies.
- Throttled to `FACE_ID_INTERVAL_S` (default 3 s) so it never saturates CPU.

Tested: "Remember my face as Hussein" → enrolled; "Do you recognize my face?" → "Hello Hocine!"

---

## 4. Always-on streaming (browser-driven)

- `WS /ws/perception-input` — device camera (PC **or** phone) → canvas frames →
  server MediaPipe → live feedback. **Zero idle CPU** when the button is off.
- Frontend `frontend/index.html` — "👁 Watch me" toggle, mirrored selfie preview,
  6 fps frame capture, live status line.
- Endpoints: `POST /vision/perceive`, `POST /api/face/enroll`,
  `GET /api/perception/status`.

Config (`backend/core/config.py`): `PERCEPTION_ENABLED`, `PERCEPTION_FPS`,
`FACE_ID_ENABLED`, `FACE_ID_MODEL`, `FACE_ID_INTERVAL_S`.

---

## 5. Proactive reactions

Wired the always-on stream to `proactive_tts` so Plasma speaks on its own:
- **Greets by name** when it recognises someone (cooldown 5 min).
- **"You look tired"** after ~10 consecutive sleepy frames (cooldown 2 min).
- Frontend connects to `WS /ws/alerts`, shows an animated **toast** + plays TTS.

Commit: `89997e8`.

### Bug found during live test + fix

DeepFace loads TensorFlow on its **first** call (~30–60 s). The original code
`await asyncio.to_thread(face_id.identify, frame)` blocked the whole frame loop
for that time → browser saw silence and disconnected before any greeting.

**Fix (`0f04608`):** run identify as a fire-and-forget `asyncio.create_task`.
Frames keep flowing; the result is collected when the task finishes; a new task
starts once `FACE_ID_INTERVAL_S` elapses. Task cancelled cleanly on disconnect.
After the first cold start, identity is instant (TF stays cached in-process).

---

## Tests

- `tests/test_vision_perception.py` — 25 tests (pure functions + skill integration).
- `tests/test_locate_and_imagegen.py` — locate fallback tests.
- All 56 vision/locate tests pass. (`faster_whisper`-dependent tests are skipped
  in CI sandbox — optional heavy dep, unrelated.)

---

## Status

| Item | State |
|------|-------|
| moondream "find my X" | ✅ working |
| Finger count / gestures | ✅ working |
| Expression (happy/sleepy/wink) | ✅ working |
| Face identity | ✅ working |
| Proactive greet + sleepy alert | ✅ shipped (non-blocking identity fix in) |

## 6. JARVIS avatar — neural-network galaxy

Canvas avatar in `frontend/index.html`, above the status bar. A swarm of
"neurons" orbits the centre like a galaxy disk (inner ones spin faster →
real swirl), nearby neurons link into a shifting neural net, and colours flow
continuously. The whole thing **pulses live with the TTS voice** — the lip-sync
Web Audio analyser feeds `avatarLevel` (0..1), which drives node size, link
density, glow, and orbit speed.

Per-state palette + motion:
- **idle** → blue→violet, slow calm swirl
- **listening** → magenta, faster spin
- **thinking** → teal, medium
- **speaking** → full-spectrum, pulses with the voice (replies + proactive alerts)

Respects `prefers-reduced-motion` (fewer nodes, no extra motion). Verified by
headless-Chromium screenshots of all four states.

### 6b. High-quality glow overhaul (reference-inspired)

Upgraded the whole frontend to a premium sci-fi look (from user reference art):
- **Avatar v2** — pseudo-**3D glass-node sphere**: nodes on a rotating Fibonacci
  sphere, perspective-projected and depth-sorted; glassy bodies with specular
  highlights; **fibre-optic light ribbons** (cyan/magenta/orange/violet) flowing
  through; **bokeh depth orbs** behind. Additive (`lighter`) compositing for glow.
- **Living backdrop** (`#bg-canvas`) — full-screen drifting bokeh + flowing light
  streams behind all content; deep-space nebula gradient on `body`.
- **Glassmorphism chrome** — talk button, waveform, and conversation log get
  translucent `backdrop-filter` blur, glowing borders, and neon shadows.

All canvas; no libraries. Respects `prefers-reduced-motion`. Verified with
headless-Chromium full-page + close-up screenshots.

---

## 7. Real-time object tracking (from the forked repos)

Researched three of the user's repos and integrated the highest-value feature:

- **locate-anything.cpp** — NVIDIA LocateAnything-3B ported to C++/ggml. Accurate
  open-vocab boxes, CPU-friendly, single-image. = Plasma's accurate locate tier.
- **VLM-AutoYOLO** — LocateAnything auto-label → SAM2/SAM3 → train YOLO. Heavy
  (12 GB VRAM, AGPL, Postgres). Documented as power-user "train your own object".
- **Handy-speech** — offline STT (Silero VAD, Parakeet V3, dictionary). Mostly
  already covered by Plasma.

**Built:** real-time object **tracking** — the gap all three pointed at. Plasma
already *detects* objects (MediaPipe EfficientDet); added the tracking layer:
- `backend/modules/vision/tracker.py` — pure-Python SORT-lite: IoU matching →
  **persistent track IDs**, velocity/direction, retire-after-max-age. No new deps.
- **Judgment call:** VLM-AutoYOLO uses Ultralytics YOLO (**AGPL-3.0**); Plasma's
  `detector.py` explicitly avoids AGPL. So we track on top of the Apache-2.0
  detector instead of bolting on AGPL YOLO — same outcome, license-clean.
- Wired into `/ws/perception-input` (opt-in `track:true`, throttled to `TRACK_FPS`).
- Frontend: **🎯 Track objects** toggle draws coloured boxes + `label #id →` over
  the live camera feed (overlay canvas, mirror-corrected labels).
- Config: `TRACK_ENABLED/CONF/FPS/MAX_AGE`. Tests: `tests/test_vision_tracker.py` (10).

---

## 8. Box on "find my X" — annotated frame in the chat

When you say "find my keys/bottle/phone", Plasma now draws the **bounding box**
on the captured frame and shows that image inline in the conversation, while the
spoken reply stays clean text.

- `locate.py` `_annotate_object()` runs the already-shipped MediaPipe EfficientDet
  detector (offline, Apache 2.0) on the captured frame; if the object class is
  found it draws a green box + label, saves `.plasma/locate_last.jpg`, and stashes
  the path via a `_set_last_annotated` / `pop_last_annotated` side channel.
- `/voice/chat` pops the path and returns it as `image_b64`; the frontend
  `addImageTurn()` renders it (with a glowing border) in the chat log.
- Objects outside EfficientDet's 80 classes still get the text answer from the
  vision tiers; locate-anything.cpp's precise boxes can feed the same channel later.
- Tests: 4 added to `tests/test_locate_and_imagegen.py` (side channel + match/no-match).

---

## 9. Phone camera page

`GET /camera` → `frontend/camera.html`: a full-screen, touch-first mobile page
that streams the phone's camera to `/ws/perception-input` (faces, gestures,
identity, object tracking — no new backend). Front/back camera flip (back by
default for objects; front mirrors for selfie), a 🎯 Track toggle with the same
smooth interpolated boxes as desktop, glass status bar, safe-area insets.
Detects the non-secure-origin gotcha (phones block getUserMedia on plain http)
and tells the user to use https/tunnel. Linked from the desktop UI.

## 9b. Turnkey HTTPS so the phone camera actually works

Phones block `getUserMedia` on plain http:// — the real blocker for the phone
page. Fixed with a one-command HTTPS launcher:
- `backend/core/tls.py` — self-signed cert generator (`cryptography`), bakes the
  machine's LAN IPs into the cert SANs, caches in `.plasma/certs/`, regenerates
  when the IP changes. Pure + unit-tested (`tests/test_tls.py`, 5 tests).
- `serve_phone.py` — generates the cert, prints `https://<lan-ip>:8443/camera`,
  serves Plasma over TLS via uvicorn.
- `GET /api/network-info` returns LAN IPs + phone URLs; desktop UI shows it on the
  phone-camera link. camera.html's error now points at `serve_phone.py`.

---

## Next (not started)

- **Train-your-own-object** — auto-label your specific keys/wallet, track in real time.
- **Demo video** for README (PA-86).

---

## Commits today

```
0f04608 fix(vision): non-blocking DeepFace identity — fire-and-forget task
89997e8 feat(vision): proactive reactions — greet by name + sleepy alert
4a90469 feat(vision): face expression + hand gesture + face recognition
7d779d3 docs: record describe-and-search fallback for moondream
b6dca4c fix(locate): describe-and-search fallback when moondream blanks
09d8725 fix(locate): ultra-short moondream prompt to fix empty responses
```
