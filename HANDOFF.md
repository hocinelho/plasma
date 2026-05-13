# Plasma — Session Handoff

> Read this at the start of every new session. Update it at the end.
> Last updated: **2026-05-13** — session by Claude Opus 4.7

---

## What was done today (2026-05-13)

### Sprint 1 — Cloud LLM (PA-25 epic)
| Ticket | What | Commit |
|---|---|---|
| PA-28 | PII redactor — regex strips emails, phones, cards, IPs, long IDs from all outbound messages | a5150a2 |
| PA-29 | Cloud LLM client — OpenAI-compatible, Groq initially | 45f7346 |
| PA-29.1 | Refactored GROQ_* → CLOUD_* (provider-agnostic); Gemini free tier as default | f916ad7 |
| PA-30 | Audit log — every cloud call appends JSONL to `.plasma/audit.log` | 23b4ac2 |
| PA-31 | Offline fallback — `chat_service._llm_reply()` tries cloud first, falls back to Ollama on any error | built into chat_service |

### Sprint 2 — UI essentials (PA-36 epic)
| Ticket | What | Commit |
|---|---|---|
| PA-37 | Waveform visualizer — Web Audio API canvas, appears only while recording | 926b127 |
| PA-38 | Conversation history — timestamps per turn, Clear button, smooth scroll, empty-state hint | 926b127 |
| PA-39 | Status indicator — 4 states: idle / listening / thinking / speaking, each with colour + pulse | 926b127 |

### Extras
- `scripts/smoke_test.py` — one-shot live test: PII → cloud → audit log
- Stale "Groq" log messages cleaned up in `chat_service.py` (commit 3833332)

---

## Current app state

- **Branch:** `claude/enhance-plasma-project-cOZli`
- **Tests:** 56 passing (`pytest tests/ --ignore=tests/test_backend.py`)
- **Provider:** Google Gemini (`gemini-2.0-flash`) via OpenAI-compat endpoint — free, 1500 req/day
- **Fallback:** Ollama (`orca-mini:latest`) on any cloud error
- **Live test:** `python scripts/smoke_test.py` — all 3 checks green after correct `.env`

### Known `.env` issue on Hocine's machine
The user set `CLOUD_BASE_URL=https://https://aistudio.google.com/api-keys` — that is WRONG.
The correct value is:
```
CLOUD_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```
Remind him to fix this at the start of next session and re-run `python scripts/smoke_test.py`.

### Known local bug on Hocine's machine
`backend/skills/get_date.py` had its content replaced by JSON on his machine.
Fix: `git checkout -- backend/skills/get_date.py`
He ran this command — should be resolved, but confirm next session.

---

## What's next — Sprint 3 (Jun 10 – Jun 24)

**Goal:** Wake word — "Hey Plasma" hands-free activation

| Ticket | What |
|---|---|
| PA-34 | `openWakeWord` integration — detect "hey plasma" in real time |
| PA-35 | Remove F9 hotkey once wake word is stable |

**Before starting PA-34:**
1. Confirm `python scripts/smoke_test.py` all green (Gemini working)
2. Confirm `get_date.py` skill loads (no IndentationError in startup log)
3. Then: `pip install openwakeword` and design the background mic thread

---

## Architecture reminder

```
Browser mic → WebM → FFmpeg → int16 PCM 16kHz
  → Whisper ASR → text
  → SkillRegistry.find_by_trigger() — fast path
  → _llm_reply() — cloud (Gemini) or Ollama fallback
  → PII redacted before any cloud send
  → Audit log written for every cloud call
  → Piper TTS → WAV → base64 → browser
```

---

## File map (key files only)

| File | Purpose |
|---|---|
| `backend/core/config.py` | All env vars — CLOUD_*, OLLAMA_*, WHISPER_MODEL |
| `backend/modules/router/cloud_client.py` | Provider-agnostic Gemini/Cerebras/OpenRouter client |
| `backend/modules/router/chat_service.py` | Glue: memory + skills + LLM + suggester |
| `backend/modules/router/pii_redactor.py` | Strips PII before cloud sends |
| `backend/modules/router/audit_log.py` | JSONL appender → `.plasma/audit.log` |
| `backend/modules/router/ollama_client.py` | Local Ollama fallback |
| `backend/skills/*.py` | Individual skill files (META + run + self_test) |
| `frontend/index.html` | Entire UI — waveform + history + status indicator |
| `scripts/smoke_test.py` | Live integration test (PA-28 + PA-29 + PA-30) |
| `JIRA.md` | Jira board mirror — always keep in sync |
| `HANDOFF.md` | This file — session memory |

---

## Rules for next session

1. **Read this file + JIRA.md before touching code**
2. **Branch is `claude/enhance-plasma-project-cOZli`** — push here, not main
3. **Before committing:** `pytest tests/ --ignore=tests/test_backend.py` must be 56+ green
4. **Every shipped feature** → update JIRA.md row + commit hash
5. **Never put API keys in code or chat** — `.env` only
6. **Commit format:** `PA-<n>: short description`
7. **Push after every commit** — set remote before each push (proxy resets it each session)

---

## Git push reminder (do this every session before first push)

```bash
git remote set-url origin https://YOUR_GITHUB_PAT@github.com/hocinelho/plasma.git
```
(Get your PAT from GitHub → Settings → Developer settings → Personal access tokens)
