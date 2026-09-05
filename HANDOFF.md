# Plasma — Session Handoff

> Read this at the start of every new session. Update it at the end.
> Last updated: **2026-08-27** — phone / wallpaper / Android / performance session
> Previous: 2026-07-15 — avatar session

---

## What was done this session (2026-08-27)

Branch: `claude/avatar-design`. All pushed.

| Commit | What |
|---|---|
| `1349240` | `piper-tts` was missing from `requirements.txt` entirely — TTS could never install |
| `e042423` | `serve_phone.py` died with a raw traceback when `cryptography` was absent; now prints the fix. `doctor.py` had said "everything checks out" moments before — it wasn't checking it |
| `28093bc` | **Wallpaper studio** at `/wallpaper` — pose her, freeze a clip mid-motion, export a PNG at the phone's true pixel size on a transparent background |
| `7da2347` | **Summon mode** `/?stage=1` — arrives full screen with the mic already open; an iOS Shortcut makes "Hey Siri, Plasma" the wake phrase |
| `93d8784` | **Android companion** (`android/`) — floating avatar over the home screen, a transparent WebView on `/?overlay=1`. **Never compiled or run — no Android SDK available.** |
| `65ef603` | `keep_alive` + `num_predict` on every Ollama request; `docs/performance.md` |

### Platform facts worth not re-deriving
- **A web page cannot draw over a phone's home screen.** No browser, either OS.
- **iOS has no overlay API at all** — not for web, not for native App Store
  apps. Siri can do it because Siri *is* the OS. The ceiling on iPhone is the
  wallpaper (`/wallpaper`) plus the Siri summon (`/?stage=1`).
- **Android can** — `SYSTEM_ALERT_WINDOW`, the permission behind Messenger's
  chat heads. That is what `android/` uses. Hocine's phone in his screenshots
  is an **iPhone**, so the Android app only helps if he gets a second device.
- TalkingHead's `playPose()` only ever takes **keyframe 0** — for `waving`
  that is arms-down, before the wave. Hence "play the clip and freeze it" in
  the wallpaper studio.
- The vendored TalkingHead carries one local patch: `preserveDrawingBuffer:
  true`, without which every wallpaper export comes back blank. A test pins it
  (`tests/test_wallpaper.py`) because a vendor refresh would silently drop it.

### Environment note
The container was reset mid-session and came back with a **stale checkout on a
branch that never existed on the remote** (`claude/avatar-design-fia8sd`).
Nothing was lost — everything lives on `origin/claude/avatar-design`. If the
tree ever looks truncated (e.g. `index.html` at 270 lines instead of ~1700),
that is the cause: `git fetch origin` and re-checkout, don't re-create work.

---

## What was done this session (2026-07-15) — Avatar

**Branch:** `claude/avatar-design` (off `claude/enhance-plasma-project-cOZli`)
**PR:** [#3](https://github.com/hocinelho/plasma/pull/3) — draft, into the enhance branch. **Not merged yet.**

| Step | What | Commit |
|---|---|---|
| 1 | Extracted avatar out of index.html → `frontend/avatar.js` + `avatar.css`, served at `/avatar.js` + `/avatar.css`; contract (`avatarState`/`avatarLevel`/`avatarWakeBurst`) preserved | 2782925 |
| 2 | Built "Plasma" mascot creature renderer (jelly body, eyes/blink/gaze, lip-sync mouth, antenna, per-state moods, wake sparkle) + wrote `docs/avatar-design.md` | fdb86fe |
| 3 | **Realistic full-body 3D human avatar** (now default) using MIT [TalkingHead](https://github.com/met4citizen/TalkingHead) + three.js 0.180, all vendored locally (`frontend/vendor/`, `frontend/avatars/brunette.glb`), static mounts `/vendor` + `/avatars`; real lip-sync from Piper audio via new optional hook `window.avatarSpeak(b64, text)` (en+de viseme modules); moods/gaze/gestures mapped to states; wave on wake word; auto-fallback to mascot if WebGL/module load fails | 282bac6 |
| 4 | Full-body camera view by default (`data-avatar-view="full|mid|upper|head"` to change) | 8e22293 |

**Renderer selection:** `<canvas id="avatar" data-avatar="human|mascot|orb">` — default `human`.

**Verified:** `node --check` both scripts; `main.py` compiles; routes serve with correct content-types; headless Chromium (SwiftShader) renders all states, speaks, waves — no page errors. Screenshots were sent to Hocine and he ran it locally in PyCharm (`python run_plasma.py`; PowerShell needs the `python` prefix).

### Key design facts (avatar)
- `avatar.js` loads **before** the main inline script and establishes the globals; index.html's `playBase64Audio(b64, text)` calls `window.avatarSpeak` first, falls back to plain `<audio>` + `avatarLevel` amplitude lip-sync.
- Character is swappable: any full-body GLB **with ARKit/Oculus viseme blend shapes + Mixamo-compatible rig** (Ready Player Me / Avaturn style) → drop in `frontend/avatars/`, change URL in `avatar.js` `showAvatar()`.
- Hocine's uploaded models: `girl_mechanic.glb` (rigged body, **no face shapes** → can't talk), `ROY_CHAR.obj` (OBJ = static, **no rig/shapes possible**). Neither usable without Blender rigging work.
- **Ready Player Me is DEAD** — Netflix acquired it (Dec 2025) and the creator/API/PlayerZero went offline **31 Jan 2026**. That's why hocine couldn't open it; it isn't a network block. Existing exported GLBs still work. Replacements: Avaturn, Avatar SDK / MetaPerson (cartoon style, selfie→GLB, first avatar free), VRoid (anime VRM), MakeHuman/MPFB (offline).
- **Hocine's quality target: Pixar/Disney-style stylized characters** (sent reference renders 2026-07-15). Those references are 2D images, not riggable models. Tradeoff triangle: stylized art / working face rig / free — pick two. See "What's next" below.
- Full docs in `docs/avatar-design.md` (concept, contract, states, asset table, swap guide).

---

## 📋 REQUESTED 2026-09-03 — the "she should really see and react" list

Six asks, in the order they should be done.

**Already worked before this list — check before building:** hand gestures
are classified every frame (`perception.classify_gesture` → thumbs_up,
open_palm, victory, pointing, fist, plus `raised`), and faces can be
enrolled and recognised by name (`vision/face_id.py`: `enroll()`,
`identify()`, "remember my face"). What was missing was not the detection —
it was that neither reached the conversation.

1. **Vision must actually run.** mediapipe + opencv-python were never
   installed on the work laptop, which is why tracking closed instantly.
   mediapipe 1.0.1 ships a pure-`py3` Windows wheel, so Python 3.13 is fine.
   Not code — a `pip install -r requirements.txt` gap. Still open; ask
   Hocine to confirm it's installed.

2. **Better recognition.** ✅ Done (`c9664cc`). The real cause of "not
   accurate" was `.env` pointing at moondream — the weakest vision model
   installed — while llama3.2-vision sat unused. Plasma now auto-selects the
   best installed Ollama vision model when none is configured, ranked
   qwen2.5-VL/MiniCPM-V > llama3.2-vision > LLaVA > moondream. A real
   open-vocabulary *detector* (boxes for arbitrary prompts, not just a
   description) is still undone — OWLv2 or Grounding DINO (Apache-2.0);
   **do not use YOLO-World**, it is AGPL through ultralytics and this repo
   is public.

3. **Gestures as meaning, not telemetry.** Still open, in the large sense
   Hocine meant ("thumbs up while she's asking something = yes", fed to the
   LLM as context). What IS done is a narrower slice that came in as its own
   ask: a raised hand at the camera makes her wave back and say hello,
   proactively — `backend/modules/vision/reactions.py`
   (`DebouncedTrigger` — 3 consecutive frames, 15s cooldown, fully unit
   tested) wired into `/ws/perception-input`, `proactive_tts.fire()` now
   carries an optional `gesture`, played via the existing `/ws/alerts` path.
   Turned on with `&watch=1` on any stage/overlay URL (off by default
   elsewhere — a camera prompt should never be a surprise). The
   context-injection half (gesture → LLM prompt, "yes"/"stop" semantics) is
   NOT built.

4. **Barge-in.** ✅ Done (`505563a`). Reaching for the mic or saying "hey
   Plasma" while she is speaking cuts her off — audio, lip-sync and any
   queued routine all stop; the reply already given stays in memory (written
   before TTS ever runs) so nothing is forgotten. Verified in Chromium: turn
   released in ~0.4s instead of waiting out the full clip.
   **Known limit, not fixed:** this is press/wake-word-to-interrupt, not
   true always-listening barge-in — she can't hear you start talking while
   her own audio plays, because that needs continuous mic capture with echo
   cancellation (the mic would otherwise hear her and interrupt herself).

5. **Corner mode.** Split by platform, both done today:
   - **Browser / phone:** she no longer paces on her own in stage/overlay
     mode (the autonomous `wander()` timer — side-to-side drift plus
     walk-left/right clips — is removed entirely; "she is moving alone, she
     must stand" was this). Ambient motion is now `idle-breathing` and
     nothing else — it used to be a random pick from every `idle-*` clip,
     which still read as fidgeting. She only moves for a request or a
     reaction.
   - **Windows desktop:** ✅ `scripts/desktop_overlay.py` — pywebview,
     frameless + always-on-top, loads the same `/?overlay=1` page the
     Android app uses, sits in a screen corner (configurable), drag to move.
   - **Only her body, no window** (four failed attempts before this one).
     Making WebView2 composite transparently does not work: Chromium renders
     through DirectComposition, so neither `LWA_COLORKEY` nor
     `SetWindowCompositionAttribute` can reach its pixels — you get a box
     that changes colour, not a box that goes away. The fix is to stop
     trying: **clip the window to her silhouette with `SetWindowRgn`**
     (`PLASMA_OVERLAY_TRANSPARENCY=shape`, the default). The page reads her
     alpha off the WebGL canvas, downscaled to ~100px, and reports scanline
     runs ~9×/s; Python scales them and applies one `ExtCreateRegion`. The
     OS clips *around* the content, so the renderer is irrelevant, and
     regions clip mouse input too — click-through comes free. Hard edges are
     the trade-off (a sticker cut-out, like every Windows desktop pet).
     No new dependency. `alpha`/`colorkey` are kept as alternatives.
   - **NOT tested on a real Windows machine** — no display available here.
     The two pieces of arithmetic that can be silently wrong *are* tested:
     corner placement, and the run→region scaling (plus the page-side
     scanline walker, run under node). See `docs/desktop-overlay.md`.

6. **Face memory with a name, from one sighting.** Still open.
   `face_id.enroll()` exists; the gap is doing it conversationally ("this is
   Anna") and recalling it unprompted on the next sighting.

---

## ⏸ PARKED — waiting on the company server (agreed 2026-08-27)

Hocine will get access to a **company server: strong compute, ~20 TB storage**.
Two pieces of work were deliberately deferred until then. Do not start either
on the laptop — both are bottlenecked by hardware, not by code.

### 1. Sentence-by-sentence speech (the real fix for lag)

The largest remaining performance win, and it is **not built**. Today nothing
is heard until *all three* stages finish: Whisper transcribes, the model
writes the **whole** reply, Piper renders the **whole** reply, and only then
does audio reach the browser.

```
now:     time-to-first-sound = asr + llm(entire reply) + tts(entire reply)   ~6-12 s
target:  time-to-first-sound = asr + llm(first sentence) + tts(one sentence) ~1-2 s
```

What it needs:

- `chat_first_sentence()` in `backend/modules/router/ollama_client.py`
  already streams tokens from Ollama — reuse it, but yield sentences instead
  of collecting the whole reply.
- A sentence splitter over the token stream (flush on `.!?` + whitespace,
  with a hard flush after N characters so a model that never punctuates
  cannot stall it).
- `/voice/chat/stream` returning NDJSON:
  `{transcript}` → `{chunk, index, text, audio_b64}` per sentence → `{done}`.
  Keep `/voice/chat` as-is so nothing that exists today breaks.
- Frontend `sendAudio()` consumes the stream, queues the chunks and plays
  them back to back, calling `avatarSpeak(b64, text)` per chunk so lip-sync
  still lines up.

Care needed: the avatar contract (`avatarSpeak`) is per-utterance, so the
gesture/routine pacing that keys off `audio.duration` has to be re-based on
the *first* chunk, not the whole reply.

### 2. A genuinely strong model

The server changes what is possible. Ranked by what its hardware allows:

| If the server has | Run | Why |
|---|---|---|
| 1× 24 GB GPU | `qwen3:30b-a3b` | MoE, ~3B active per token — big-model answers at small-model speed |
| 2× 48 GB+ / 96 GB VRAM | `glm-4.5-air` (106B, 12B active) | frontier-adjacent, still fast enough to speak |
| a real rack | `glm-4.6` (355B) or Kimi K2 | what Hocine actually asked for; ~1T params for K2 |
| no GPU, lots of RAM | `qwen3:14b` | dense, honest fallback |

20 TB is far more than the models need (the largest are tens of GB) — the
storage matters for **Whisper `large-v3`**, meeting recordings, and keeping
every model pulled at once rather than juggling them.

Serve it with `OLLAMA_HOST=0.0.0.0` on the server and point the laptop at it:
`OLLAMA_BASE_URL=http://<server>:11434`. No code change — see
[`docs/distributed-setup.md`](docs/distributed-setup.md).

**Before touching either:** open `/analytics` and read the real `asr_ms` /
`llm_ms` / `tts_ms` per turn. Plasma already logs all three. Do not optimise
by guessing — [`docs/performance.md`](docs/performance.md) explains how to
read them.

### Also still unanswered
- Hocine's laptop specs (GPU / VRAM / RAM) were never established. Ask, or
  have him run `python scripts/doctor.py`.
- **Her asking *him* questions** — the missing half of "realistic
  interaction". Offered, never steered on flavour or frequency.

---

## What's next — agreed option menu (Hocine to pick; none started)

### Changing the character (target: Pixar/Disney-stylized look)
1. Drop-in GLB swap (works today, minutes) — needs viseme blend shapes
2. **Avatar SDK / MetaPerson** — has a *cartoon* style, selfie→GLB w/ Mixamo rig, first avatar free
3. **VRM route** (VRoid Studio / VRoid Hub) — thousands of free stylized characters; VRM *guarantees* mouth blendshapes by spec; needs a one-time VRM→GLB conversion (or switch renderer to three-vrm)
4. Avaturn (realistic-leaning), MakeHuman/MPFB (offline, free)
5. Character Creator 4 (Reallusion) — paid (~$300), the actual industry route to that render quality with full ARKit visemes
6. Sketchfab stylized model + Blender viseme sculpting — free but hours of manual work
7. **UI avatar picker** — dropdown listing GLBs in `frontend/avatars/` (to build)

### Adding movement
1. Map more built-in TalkingHead gestures/poses to states (shrug on unknown, thumbs-up on success) — small
2. **Mixamo animations** (free) — idle variety, dance, stretch; TalkingHead plays Mixamo FBX directly — medium
3. **Voice-command moves** — "dance"/"tanz mal" skill → playAnimation — medium
4. **Sentiment-driven moods** — backend tags reply emotion → she looks happy/sad about content, not just pipeline state — medium
5. Gaze follows user via existing camera vision — bigger

Recommended combo: Mixamo idles + dance skill + sentiment moods; Avaturn for the character; then UI picker.

---

## Current app state

- **Working branches:** `claude/avatar-design` (avatar, PR #3 open) ← based on `claude/enhance-plasma-project-cOZli` (main dev branch, everything else)
- **App:** FastAPI backend (`python run_plasma.py`, port 8000), single-page UI `frontend/index.html`
- **Provider:** Gemini via OpenAI-compat endpoint, Ollama fallback; PII redaction + audit log on cloud calls
- Since the old May handoff, the enhance branch also gained: wake word + clap detector, WiFi sensing (RuView skeletons/floor-plan), vision (face/gesture/object tracking), KaTeX math rendering, analytics page, setup wizard

---

## Architecture reminder

```
Browser mic → WebM → FFmpeg → int16 PCM 16kHz
  → Whisper ASR → text
  → SkillRegistry.find_by_trigger() — fast path
  → _llm_reply() — cloud (Gemini) or Ollama fallback
  → PII redacted before any cloud send; audit log per cloud call
  → Piper TTS → WAV → base64 → browser
  → avatar lip-syncs: avatarSpeak(b64, text) (human 3D) or avatarLevel pulse
```

---

## File map (key files)

| File | Purpose |
|---|---|
| `frontend/index.html` | Main UI (importmap + avatarSpeak hook added) |
| `frontend/avatar.js` | All 3 avatar renderers + contract (human/mascot/orb) |
| `frontend/avatar.css` | Avatar styles (`#avatar`, `#avatar-human`) |
| `frontend/vendor/talkinghead/` | TalkingHead + retargeter + dynamicbones + lipsync-en/de (MIT) |
| `frontend/vendor/three/` | three.js 0.180 module + addons (MIT) |
| `frontend/avatars/brunette.glb` | Default 3D character (MIT, from TalkingHead repo) |
| `docs/avatar-design.md` | Avatar design doc — read before avatar work |
| `backend/main.py` | Routes incl. `/avatar.js`, `/avatar.css`, `/vendor`, `/avatars` mounts |
| `backend/modules/router/chat_service.py` | Glue: memory + skills + LLM |
| `backend/skills/*.py` | Skill files (META + run + self_test) |
| `JIRA.md` | Jira board mirror |
| `HANDOFF.md` | This file — session memory |

---

## Rules for next session

1. **Read this file + `docs/avatar-design.md` (for avatar work) + JIRA.md before touching code**
2. Avatar work continues on `claude/avatar-design` until PR #3 merges; other work on `claude/enhance-plasma-project-cOZli`
3. Before committing: `pytest tests/ --ignore=tests/test_backend.py` must stay green
4. Never put API keys in code or chat — `.env` only
5. Push after every commit
6. Avatar contract is sacred: `avatarState`, `avatarLevel`, `avatarWakeBurst()`, optional `avatarSpeak(b64, text)` — anything new must keep these working
