# Plasma — Session Handoff

> Read this at the start of every new session. Update it at the end.
> Last updated: **2026-07-10** — Claude Code web session

---

## Branch situation (read first)

- **All real work lives on `claude/enhance-plasma-project-cOZli`** (v1.0.0 shipped 2026-06-11, then vision + sense work). 
- **`main` is frozen at 2026-04-28** (Step 8, pre-v1.0) — 200+ commits behind. Its README/handoff.py are obsolete; don't trust them.
- **PR #2 (open, draft):** `claude/session-015ndjdsamrc9cy69awrrpeb-x6de9z` → enhance branch — Level 1 RSSI sensing (see below). Merge it if tests are green.
- `.plasma/MEMORY.md` is gitignored — it only exists on Hocine's machine. THIS file is the shared memory; keep it updated **every session**.

## What was done last (2026-07-10)

**Level 1 real WiFi sensing — laptop RSSI motion detection (PR #2).**
Until now all WiFi sensing was the simulated demo. Now:

| Piece | What |
|---|---|
| `backend/modules/sense/rssi_sensor.py` | Stdlib-only `MotionDetector`: RSSI jitter (sliding-window sigma) vs adaptive quiet baseline; presence = motion within last `--hold` s (default 600). Readers: `netsh` (Windows, en+de) / `/proc/net/wireless` (Linux). |
| `scripts/ruview_bridge.py --rssi` | Third bridge mode (demo / real / **rssi**). Same `/api/presence` + `/api/pose` endpoints → `wifi_sense` skill, alerts, and UI work unchanged. Honest shape: count 0/1, no rooms/pose/vitals. |
| `tests/test_rssi_sensor.py` | 11 tests: parsers (en/de netsh, proc), motion/hold/warmup logic, Windows-blocker hints. |

**⛔ Real-world test BLOCKED on Hocine's machine:** it's a **company laptop** — Windows 11 24H2 hides `netsh wlan` signal info unless **Location Services** are enabled (company policy forbids) or the shell runs **as Administrator**. The bridge now prints this exact diagnosis at startup. Untested paths: a private machine, an elevated shell, or the phone-hotspot test. Feature is code-complete + unit-tested, awaiting a live test.

**Hardware context:** Hocine's gateway is a Teltonika TRB500 — **5G only, no WiFi radio**, unusable as a sensor. Real through-wall sensing = ESP32-S3 (~9€) + ESP-CSI → `real_scene()` in the bridge ("Level 2", not started).

## What's next (agreed with Hocine)

1. **Vision detection upgrade** — Hocine is NOT satisfied with current detection. Plan: integrate **https://github.com/hocinelho/supervision** (his fork of Roboflow Supervision: detection post-processing, tracking, annotation) into `backend/modules/vision/` (detector/tracker). Start by reading `vision/detector.py`, `tracker.py`, `perception.py` and `docs/locate-vision-status.md`.
2. Level 1 RSSI live test whenever a non-locked-down WiFi machine is available.
3. Level 2: ESP32-S3 CSI → bridge `real_scene()` (hardware not ordered yet).

## ⚠️ Standing warnings

- **Old `main` has a real Groq API key committed in `.env.example`** (`gsk_...`). Told Hocine to revoke it at console.groq.com — as of 2026-07-10 unconfirmed. Never commit real keys; `.env.example` gets placeholders only.
- Do **not** commit `voices/*.onnx` (60 MB models) or `external/locate-anything.cpp` (embedded git repo). A local WIP commit with these existed on Hocine's machine (2923ce0) — advised `git reset --soft HEAD~1`; confirm it never got pushed.
- Files on `main` (`README.md`, `.gitignore`, `handoff.py`) contain broken PowerShell here-string wrappers (`@" ... "@ | Out-File`). Don't create files that way.

## Architecture reminder

```
Browser mic → WebM → FFmpeg → int16 PCM 16 kHz
  → Whisper ASR → text
  → SkillRegistry.find_by_trigger() — fast path (45 skills)
  → _llm_reply() — cloud (Gemini via OpenAI-compat) or Ollama fallback
  → PII redacted before any cloud send; audit log per cloud call
  → Piper TTS → WAV → base64 → browser
Sense layer: ruview_bridge (demo | rssi | real-CSI) → /api/wifi/scene
  → wifi_sense skill, RuViewMonitor alerts, see-through + floor-plan UI
Vision layer: camera → detector/tracker/face_id/perception → vision skills
```

## File map (key files only)

| File | Purpose |
|---|---|
| `backend/core/config.py` | All env vars — CLOUD_*, OLLAMA_*, WHISPER_*, RUVIEW_* |
| `backend/modules/router/` | chat glue, cloud client, PII redactor, audit log, Ollama |
| `backend/modules/sense/` | RuView monitor, floor plan, **rssi_sensor (new)** |
| `backend/modules/vision/` | capture, detector, tracker, face_id, perception — next work area |
| `backend/skills/*.py` | 45 skills (META + run + self_test) |
| `scripts/ruview_bridge.py` | WiFi-sensing bridge: demo / **--rssi** / real ESP32 hook |
| `frontend/index.html` | Main UI (see-through view, wake burst, KaTeX) |
| `JIRA.md` | Ticket board mirror |
| `HANDOFF.md` | This file — session memory. **Update before ending a session.** |
| `docs/session-log-*.md` | Per-session detail logs |

## Rules for next session

1. **Read this file first** — don't trust `main`'s README/handoff.py (frozen at April).
2. Work branches off `claude/enhance-plasma-project-cOZli`; web sessions push their own `claude/session-*` branch + PR into it.
3. Before committing: `pytest tests/` green (CI runs on push to main + enhance branch only, NOT on PRs into enhance — run tests locally).
4. Every shipped feature → update JIRA.md and THIS file (state + blockers + next steps).
5. Never put API keys in code, chat, or `.env.example` — `.env` only.
6. Skill files: `backend/skills/<name>.py` with META + run + self_test; framework in `backend/modules/skills/`.
