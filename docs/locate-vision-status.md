# Vision / Locate — Work Log & Status

> Living status for the camera + "find my X" (LocateAnything) work on
> branch `claude/enhance-plasma-project-cOZli`. Update as bugs close.

_Last updated: 2026-06-25 (proactive reactions)_

---

## Goal

Make Plasma **see through the camera** and answer "find my keys" / "where is my phone":

- Work **smoothly on the PC now**, and on **phones/laptops in the future**
  (phones connect to Plasma's browser UI — all vision runs server-side).
- **No performance loss** — must not freeze the machine.
- Recognise objects by natural language (open-vocabulary).

---

## Architecture — 3-tier vision backend

Tried in priority order; each tier falls through to the next on any failure:

| Tier | Backend | Speed | Install | Notes |
|------|---------|-------|---------|-------|
| 1 | **Cloud vision LLM** (Gemini / OpenRouter) | sub-second | none (uses `CLOUD_API_KEY`) | Needs internet + working key |
| 2 | **Ollama moondream** | fast on CPU | `ollama pull moondream` (~1.9 GB) | **Offline. Current working tier.** |
| 3 | **locate-anything.cpp CLI** | 5–70 s on CPU | 6 GB GGUF + C++ build | Heavy; for power users / GPU |

Config lives in `backend/core/config.py` (`LOCATE_*` vars). The skill is
`backend/skills/locate.py`. Camera capture is `backend/modules/vision/capture.py`.

**Recommended setup (offline, reliable):** blank `CLOUD_API_KEY`, use
moondream (tier 2) + local `mistral` for chat. No cloud dependency, no API keys
to break, phones just open the PC's browser URL.

---

## ✅ Fixes shipped (all pushed to the branch)

| # | Fix | Commit |
|---|-----|--------|
| 1 | 3-tier vision backend (cloud → Ollama → CLI), tier cascade on failure | `60bdaf1`, `b4fcdbb` |
| 2 | OpenRouter URL normalization + 404 auto-retry with `CLOUD_MODEL` | `3333e4c`, `058e0b1` |
| 3 | MUAPI image-gen slug fix (`flux-schnell-image`; bare slug 404s) | `c3a6bcd` |
| 4 | Robust webcam capture — DirectShow on Windows, warmup + retry frames | `b5690d9` |
| 5 | Response polish — strip quotes, wrap bare phrases into natural sentences | `49e239f` |
| 6 | Reduce hallucination — simpler prompt + Python-side response parser | `466d6c3`, `201c795` |
| 7 | Wake word debounce (N consecutive frames) + fixed misleading log | `82cf75e` |
| 8 | Empty-moondream retry + black-frame detection + image-size logging | `2f64257` |
| 9 | Ultra-short moondream prompt (`"Where is the {obj}?"`) + expanded not-found vocab + 3 retries | `09d8725` |
| 10 | **Describe-and-search fallback** — if moondream blanks on the question, ask it to *describe* the scene, then search the description for the object | `b6dca4c` |
| 11 | **Proactive reactions** — on the always-on stream, Plasma greets you by name when it sees you, and warns "you look tired" after sustained sleepy expression. Toast + TTS. | _this commit_ |

---

## ✅ Confirmed working

- Voice → ASR (faster-whisper) → LLM → TTS (Piper) pipeline.
- **Camera + moondream located a real object** ("find my key" → "near the door").
- Fully offline path (local `mistral` chat + moondream vision).

---

## 🔧 Open bugs / needs re-test

| Bug | Status | Action needed |
|-----|--------|---------------|
| moondream returns empty response | **Fixed (2 layers)** — short native prompt, then a *describe-the-scene* fallback that searches the description in Python. moondream blanks on questions but always describes images. | Restart + try again. Log now shows `falling back to scene description` then `moondream description: ...` |
| Wake word false fires ("hello hocine" unprompted) | Debounce shipped — **re-test** | Set `WAKE_WORD_THRESHOLD=0.6`, `WAKE_WORD_TRIGGER_FRAMES=3` |
| OpenRouter every model returns 404 | **Not a code bug** — account/key issue | Use local models (recommended) or fix the OpenRouter key |

### Diagnostic: the image-size log line

After `git pull` + restart, "find my keys" prints:

```
locate: captured 640x480 image → /tmp/xxx.jpg (45.2 KB)
```

| Log shows | Meaning |
|-----------|---------|
| `< 1 KB` | Camera image is black — webcam slow/blocked by another app |
| `30+ KB` | Image is real — any failure is the vision model, not the camera |
| `Camera not available` (no size log) | Camera device isn't opening at all |

---

## .env reference (recommended offline setup)

```ini
# Go fully local — no cloud round-trips, no 404 delays
CLOUD_API_KEY=

# Local chat
OLLAMA_MODEL=mistral:latest

# Local vision (tier 2)
LOCATE_VISION_OLLAMA_MODEL=moondream

# Wake word tuning (stop false triggers)
WAKE_WORD_THRESHOLD=0.6
WAKE_WORD_TRIGGER_FRAMES=3
```

If accuracy isn't enough, swap to a bigger local vision model — no code change:

```ini
LOCATE_VISION_OLLAMA_MODEL=llama3.2-vision   # or llava:13b
```

---

## 👁 Face & gesture perception (NEW)

Plasma can now **see you**: read your face expression and hand gestures, count
fingers, and recognize who you are.

| Capability | Backend | How |
|-----------|---------|-----|
| Finger counting (0–5) | MediaPipe HandLandmarker | 21 hand keypoints → `count_fingers()` |
| Gestures: victory ✌️, thumbs up 👍, open palm, fist, pointing | MediaPipe | `classify_gesture()` |
| Expression: happy 😀 / sleepy 😴 / winking 😉 / neutral | MediaPipe FaceLandmarker blendshapes | `classify_expression()` |
| Face identity ("you're Hocine") | **DeepFace** (optional) | `face_id.identify()` against `.plasma/faces/` |

**Why MediaPipe (35.8k ⭐) not GLM-4V / Kimi-VL:** real-time tracking needs
landmark coordinates at ~30 fps on CPU. Big vision-LLMs give a paragraph per
frame (1–5 s) and would freeze the machine — wrong tool. GLM/Kimi remain an
optional plug-in for the *describe-the-scene* path (`LOCATE_CLOUD_MODEL`).

**Always-on, but safe:** perception is **browser-driven** — the web UI
"👁 Watch me" button uses the device camera (PC *or* phone), streams frames to
the server, and stops instantly when toggled off. **Zero idle CPU** when off,
and no fighting "find my keys" for the webcam. Identity (DeepFace) is throttled
to once per `FACE_ID_INTERVAL_S` so it never eats CPU.

**Voice too:** "how many fingers?", "how do I look?", "do you see me?",
"remember my face as Hocine" → `backend/skills/vision_query.py` (one-shot snapshot).

### Endpoints
| Route | Purpose |
|-------|---------|
| `POST /vision/perceive` | base64 image → expression + gestures + finger count |
| `POST /api/face/enroll` | base64 image + name → learn a face |
| `GET /api/perception/status` | deps available + enrolled people + tracking |
| `WS /ws/perception-input` | stream device-camera frames → live perception + object tracking |

---

## 🚀 Detection upgrade — supervision integration (2026-07-10)

Hocine wasn't satisfied with detection quality. Root causes: tiny
EfficientDet-Lite0 int8 model, full-frame-only inference (small objects are a
few pixels), and the greedy-IoU tracker swapping IDs on occlusion. Fixed with
**Roboflow Supervision (MIT — fits the no-AGPL policy)**:

| Change | Config | Effect |
|---|---|---|
| `sv.ByteTrack` tracker backend (Kalman + low-conf second pass + lost-track buffer) with SORT-lite auto-fallback | `TRACK_BACKEND=byte` (default) / `iou` | IDs survive occlusion/crossing; label flicker no longer kills tracks |
| SAHI tiled inference on snapshot paths ("what do you see", "find my X") via `sv.InferenceSlicer` | `VISION_SLICING=true` (default) | Small objects (keys!) become visible; live tracking loop stays full-frame for speed |
| EfficientDet-**Lite2** default (Lite0 still available) | `VISION_DETECTOR_MODEL=efficientdet_lite2` | Better raw accuracy, still Apache 2.0, ~12 MB |
| `vision/detections.py` — dict↔`sv.Detections` converters, `annotate_frame()` | — | One interop point; server-side annotated snapshots |

Install: `pip install "supervision>=0.26,<0.30"` (pinned — 0.30 removes
`ByteTrack`; migrating to Roboflow's `trackers` package is a one-line swap
noted in `tracker.py`). Everything degrades gracefully without it.
Tests: `tests/test_supervision_integration.py` (13). Not yet live-camera
tested. Phase 2 candidates: RF-DETR backend, PolygonZone room zones.

## 🎯 Real-time object tracking (NEW)

The "Watch me" feed can now **track objects with persistent IDs** and draw boxes
live. Tick **🎯 Track objects**; Plasma detects objects each frame and follows
each one with a stable id (e.g. `bottle #3 →` as it moves right).

| Layer | Backend | License |
|-------|---------|---------|
| Detection (80 classes) | MediaPipe EfficientDet-Lite0 (already shipped) | Apache 2.0 |
| Tracking (persistent IDs) | `backend/modules/vision/tracker.py` — pure-Python SORT-lite (IoU matching) | MIT (ours) |

**Why not Ultralytics YOLO + ByteTrack (as VLM-AutoYOLO uses)?** Ultralytics is
**AGPL-3.0**; Plasma deliberately stays Apache/MIT (see `detector.py`). A classic
SORT-style IoU tracker gives persistent IDs with **zero new dependencies and no
license entanglement**, runs in microseconds, and rides on the detector we
already ship. Opt-in per stream (`track:true`) → zero cost when off. Throttled to
`TRACK_FPS`; the tracker keeps IDs stable between detection cycles.

**Smooth, no-blink, multi-object.** Three layers keep boxes glued to moving
objects instead of flickering:
1. **Server coasting** — a track keeps reporting via a velocity-predicted box for
   `TRACK_COAST_FRAMES` missed detections, so one weak frame never blinks it out.
2. **Server smoothing** — the reported box is exponentially smoothed (no jitter).
3. **Client interpolation** — the browser glides each box toward its latest target
   at ~60 fps (server sends ~5 fps), so motion looks fluid.
Multi-object: a dedicated lower-threshold detector (`TRACK_CONF`, up to
`TRACK_MAX_OBJECTS`) feeds the tracker, which already handles any number at once.

Config: `TRACK_ENABLED` (true), `TRACK_CONF` (0.35), `TRACK_FPS` (5),
`TRACK_MAX_AGE` (8), `TRACK_MAX_OBJECTS` (12), `TRACK_COAST_FRAMES` (3).

### Where the forked repos fit
- **locate-anything.cpp** (NVIDIA LocateAnything-3B → C++/ggml): the *accurate,
  open-vocabulary* "find my X" tier (precise boxes, single-image, CPU-friendly
  q4_k ~4.7 GB). Already Plasma's locate tier 3.
- **VLM-AutoYOLO**: auto-label (LocateAnything) → SAM2/SAM3 masks → train a
  custom YOLO for *your* objects. Heavy (12 GB VRAM, AGPL, Postgres) — documented
  as a power-user path to make a real-time model of your specific keys/wallet,
  not bundled.
- **Handy-speech**: offline STT (Silero VAD, Parakeet V3, dictionary). Plasma
  already covers most of this; Parakeet/dictionary are future nice-to-haves.

### Setup
```ini
# Always required for tracking (auto-downloads ~16 MB of models):
#   pip install mediapipe opencv-python
# Optional — recognize WHO it sees (heavier, pulls tensorflow):
#   pip install deepface

FACE_ID_MODEL=ArcFace        # or Facenet / SFace (lighter)
PERCEPTION_FPS=6             # browser stream rate
FACE_ID_INTERVAL_S=3.0       # how often identity runs in always-on
```

Files: `backend/modules/vision/perception.py` (MediaPipe face+hand),
`backend/modules/vision/face_id.py` (DeepFace), `backend/skills/vision_query.py`,
`frontend/index.html` (Watch me button), `tests/test_vision_perception.py`.

---

## 📱 Phone camera page (NEW)

`GET /camera` (`frontend/camera.html`) — a dedicated **mobile-friendly** page:
full-screen camera stage, big touch controls, **front/back camera flip** (back by
default for objects, front mirrors for selfie/face), and a **🎯 Track** toggle
that draws smooth interpolated boxes. Streams to the same `/ws/perception-input`,
so it gets faces, gestures, identity *and* object tracking with no extra backend.
Linked from the desktop UI ("📱 Use your phone's camera →").

> Phones block `getUserMedia` on plain `http://` (non-secure origin). The page
> detects this and tells the user to use **https://** (or a tunnel). On localhost
> it works directly.

### Turnkey HTTPS for the phone — `python serve_phone.py`

Run `python serve_phone.py` and it:
1. Generates a **self-signed cert** with your computer's LAN IP in its SANs
   (`backend/core/tls.py`, cached in `.plasma/certs/`, regenerated when the IP
   changes), then serves Plasma over **HTTPS** (default port 8443) — no internet,
   accounts, or tunnels.
2. Prints the exact phone URL, e.g. `https://192.168.1.42:8443/camera`.

On the phone (same Wi-Fi) open that URL and tap **Advanced → Proceed** once to
accept the self-signed cert — then the camera works. The desktop UI fetches
`GET /api/network-info` and shows the URL on the "📱 Use your phone's camera" link.

## 🧠 Find anything + recognize anything (open-vocabulary)

Two different jobs, both now open-vocabulary via the vision LLM (moondream
offline, or a cloud VLM) — not limited to the 80-class detector:

| Ask | Skill | How |
|-----|-------|-----|
| **Find** "find the baby", "where is the remote" | `locate` | VLM locates ANY described object; draws a box when the on-board detector knows the class (locate-anything.cpp adds boxes for anything). |
| **Recognize** "what is this?", "what am I holding?", "what do you see?" | `vision` | `locate.describe_scene()` asks the VLM to name whatever is in frame — ANY object/person/animal — with the 80-class detector as fallback. |

So finding and recognizing arbitrary objects works today with **moondream**
(offline) or a cloud key — no per-object training. For **real-time tracking of
arbitrary** objects (not just the 80 classes) and precise boxes for anything, set
up **locate-anything.cpp** (tier 3) or train a small model (VLM-AutoYOLO path,
task #3).

## ⚡ Speed / latency

Biggest wins, from real-run profiling:

| Bottleneck | Was | Fix |
|-----------|-----|-----|
| **"Find X" camera open** | ~15 s every time (webcam re-opened per call) | **Warm camera cache** — open once, reuse; released after `CAMERA_KEEPALIVE_S` (60s) idle. First find is slow, the rest are ~instant. |
| **ASR (Whisper)** | ~3 s (beam 5) | `WHISPER_BEAM_SIZE=1` (greedy) default — ~2× faster, negligible loss on commands. |
| **Chat LLM** | ~5 s to first sentence | Already streams "first sentence" then stops. Use a smaller local model for more speed (below). |

**Config knobs for speed** (`.env`):
```ini
WHISPER_MODEL=base.en        # base is ~2x faster than small (tiny.en faster still)
WHISPER_BEAM_SIZE=1          # greedy decoding (default)
CAMERA_KEEPALIVE_S=60        # keep webcam warm between "find X"
OLLAMA_MODEL=llama3.2:3b     # a 3B model answers much faster than mistral 7B
LOCATE_VISION_OLLAMA_MODEL=moondream   # keep the small/fast vision model
```

For the fastest chat, a 3B model (`llama3.2:3b`, `qwen2.5:3b`, `phi3:mini`) roughly
halves LLM latency vs a 7B like mistral, with fine quality for an assistant.

## 🧷 Train-your-own-object (personal object memory)

Teach Plasma YOUR specific things — no training, offline, license-clean:

1. Hold the item up and say **"remember this as my keys"** (`remember_object`
   skill). Plasma crops to the item and stores it under `.plasma/objects/keys/`.
2. Later **"find my keys"** pins that *exact* item: it runs the detector for
   candidate boxes, embeds each with **MediaPipe ImageEmbedder** (Apache 2.0),
   and picks the one closest to your enrolled "keys" — draws the box and answers
   with the location. Falls back to the open-vocab VLM if your item isn't in view.

The VLM-AutoYOLO idea kept lightweight: **embeddings, not a trained YOLO** —
instant enrollment, no GPU, no AGPL. `backend/modules/vision/object_memory.py`.
Config: `OBJECT_MEMORY_ENABLED`, `OBJECT_MATCH_THRESHOLD` (0.55). Enrolled items
appear in `GET /api/perception/status`.

## 📋 Not started (next features)
- **Proactive reactions** — ✅ shipped: greets you by name when first seen, alerts "you look tired" after ~1.7 s of sleepy expression. Toast in the UI + TTS spoken alert.
- **JARVIS avatar + living UI** — ✅ shipped: a pseudo-**3D glass-node sphere**
  in `frontend/index.html`. Nodes sit on a rotating Fibonacci sphere
  (perspective-projected, depth-sorted), link into a neural net, with
  **fibre-optic light ribbons** (cyan/magenta/orange/violet) flowing through and
  **bokeh depth orbs** behind. Glassy nodes have specular highlights. Pulses live
  with the TTS voice (Web Audio analyser → `avatarLevel`); palette + spin shift
  per state. The whole page also gained a **living backdrop** (`#bg-canvas`:
  drifting bokeh + flowing light streams) plus glassmorphism panels/buttons.
  Respects `prefers-reduced-motion`; verified with headless-Chromium screenshots.
- **Demo video** for the README (PA-86).

---

## Key files

| File | Responsibility |
|------|----------------|
| `backend/skills/locate.py` | The "find my X" skill, 3-tier logic, response parsing |
| `backend/modules/vision/capture.py` | Webcam capture (DirectShow + warmup/retry) |
| `backend/core/config.py` | All `LOCATE_*`, `MUAPI_*`, `WAKE_WORD_*` config vars |
| `backend/modules/voice/wake_word.py` | Wake-word detector + consecutive-frame debounce |
| `backend/modules/voice/wake_monitor.py` | Mic → detector → WebSocket broadcast |
| `tests/test_locate_and_imagegen.py` | Locate + image-gen tests |
| `tests/test_vision_skill.py` | Camera capture tests |
| `tests/test_pa89_wake_word.py` | Wake-word + debounce tests |

---

## 📡 WiFi presence sensing (RuView integration)

`backend/skills/wifi_sense.py` — voice layer over **RuView** (WiFi CSI sensing:
detects people through walls, counts occupants, maps rooms — no camera).

- Ask: "is anyone home?", "who's in the living room?", "how many people are home?"
  (+ German). Falls back to clear setup guidance when RuView isn't running.
- **Hardware reality:** a laptop's WiFi only gives coarse RSSI. True CSI sensing
  needs an **ESP32-S3 (~$9)**, RPi + `nexmon_csi`, or a research NIC — OR run
  RuView's no-hardware **Docker demo**. RuView does the sensing and exposes an
  HTTP API; Plasma queries it.
- Config: `RUVIEW_ENABLED`, `RUVIEW_URL` (http://localhost:3000), `RUVIEW_API_KEY`.
- Endpoint-agnostic: probes several common RuView paths and parses presence/
  count/rooms flexibly. Tests: `tests/test_wifi_sense.py`.

Setup (no hardware):
```
docker run -p 3000:3000 ruvnet/wifi-densepose:latest
# .env:  RUVIEW_ENABLED=true   RUVIEW_URL=http://localhost:3000
```

### Proactive presence alerts
`backend/modules/sense/ruview_monitor.py` polls RuView on a daemon thread and
fires spoken **ProactiveTTS** alerts on presence changes: "Someone just arrived
home.", "Someone entered the living room.", "The house is empty now." Off by
default; enable with `RUVIEW_ALERTS=true`, or toggle by voice ("watch the house"
/ "stop watching the house"). Mirrors WakeMonitor/VisionMonitor (never blocks the
loop); `RUVIEW_POLL_S`, `RUVIEW_ALERT_COOLDOWN_S`. Tests: `tests/test_ruview_monitor.py`.

### Vitals + pro renderer + wake burst (2026-07)
- **Vitals from WiFi**: breathing (0.08–0.6 Hz band) + heart rate flow through
  the pipeline — bridge/RuView emit `breathing_bpm`/`heart_bpm` per person,
  `fetch_scene` parses them (flexible key names), and the see-through view shows
  a 🫁/❤ chip per person whose **chest visibly breathes at the sensed rate** and
  whose glow pulses at the heart rate. Voice: "what's my heart rate / breathing
  rate / check my vitals" (EN+DE). Research: >95% accuracy single-person on
  ESP32 (64 subcarriers); needs stillness + calibration in real deployments.
- **Smooth tracked renderer**: people get stable client-side IDs (nearest-
  neighbour), positions/keypoints interpolate at 60 fps between 2 Hz polls,
  motion trails, soft presence glow — no more jumpy redraws.
- **Wake burst**: "hey plasma" OR a double-clap (CLAP_WAKE_ENABLED=true) fires a
  whole-background wake-up — neural sphere surges, backdrop accelerates +
  brightens, shockwave rings expand across the page (~2.5 s).
- **Perf**: floorplan.json mtime-cached (was re-read at 2 Hz), uvicorn access
  logs for /api/wifi/scene|favicon|sw.js suppressed (console flood), see-through
  polling pauses when the tab is hidden.

### Wake burst v2 + clap false-trigger fix (2026-07)
- **Cinematic wake burst**: the previous single-ring pulse felt weak. Now on
  wake ("hey plasma" or a clap): a bright radial power-on flash, 5 colour-
  sweeping shockwave rings (ease-out, cyan→violet→amber), ~46 neural sparks
  flung outward and fading, and the avatar sphere itself flashes into a wide-
  spectrum `waking` palette (fast spin, icy-white core) for ~1.7 s before
  easing back to its normal state — the whole page visibly "wakes up," not
  just the sphere. `window.bgWakeBurst()` / `window.avatarWakeBurst()`.
- **Clap detector was way too sensitive** — normal talking and clicks near the
  mic were firing it. Root cause: the old detector only checked "peak loud
  enough vs. background," with no way to tell a real clap (energy concentrated
  in a few ms) from sustained loud speech (energy fills the whole ~80 ms
  analysis chunk) at the same peak volume. Fixed with a **crest-factor gate**
  (`CLAP_MIN_CREST`, default 5.0): require peak/RMS-within-chunk to be high
  (impulsive), which sustained talking never is. Also added an **absolute
  loudness floor** (`CLAP_MIN_PEAK`, default 1400) so a very quiet room's low
  baseline can't make faint sounds "relatively loud" enough to pass, and raised
  the default relative `CLAP_THRESHOLD` from 8 → 12. If real claps stop
  registering in an echoey room, lower `CLAP_MIN_CREST` to ~3.5–4; if clicks
  near the mic still trigger it, raise `CLAP_THRESHOLD`/`CLAP_MIN_PEAK` further.
  Tests: `tests/test_clap_detector.py` (sustained voice never triggers, loud
  syllable pairs don't count as double-claps, sub-floor transients rejected,
  genuine claps still detected under the stricter defaults).

### ⚠️ Reality check on WiFi sensing (important)
The demo (`scripts/ruview_bridge.py`) generates **entirely fake, simulated**
people/vitals — it is not sensing anyone, ever. It exists only so the UI
(see-through view, vitals, alerts) can be tested with zero hardware. To detect
real people (you, family) in a real apartment, you need actual CSI hardware —
a mesh of ESP32-S3 nodes (or an Intel 5300/AR9580 NIC) running RuView's real
sensing pipeline, feeding `RUVIEW_URL`. Without that hardware, "not accurate /
can't detect my family" is expected: there is no real signal being measured.
