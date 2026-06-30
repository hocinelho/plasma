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

## 6. Talking avatar (lip-sync)

SVG Plasma face in `frontend/index.html`, above the status bar:
- **idle** → gentle breathing glow
- **listening** → brightens (hot accent), eyes widen
- **thinking** → eyes glance side to side
- **speaking** → mouth **lip-syncs to the live TTS audio amplitude** via a Web
  Audio AnalyserNode; works for both spoken replies and proactive alerts.

Respects `prefers-reduced-motion`. Falls back to plain playback if Web Audio
is unavailable.

---

## Next (not started)

- **Phone camera page** — backend is camera-agnostic; needs a mobile-friendly UI.
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
