# Plasma — Session Handoff

> Read this at the start of every new session. Update it at the end.
> Last updated: **2026-07-15** — avatar session by Claude (Claude Code on the web)

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
- **readyplayer.me is blocked/unreachable for Hocine** — suggest Avaturn (selfie → avatar) or MakeHuman/MPFB (offline) instead.
- Full docs in `docs/avatar-design.md` (concept, contract, states, asset table, swap guide).

---

## What's next — agreed option menu (Hocine to pick; none started)

### Changing the character
1. Drop-in GLB swap (works today, minutes)
2. Avaturn selfie avatar (RPM alternative, not blocked)
3. MakeHuman/MPFB offline character design
4. VRoid Studio anime style (needs one-time Blender conversion)
5. **UI avatar picker** — dropdown listing GLBs in `frontend/avatars/` (to build)

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
