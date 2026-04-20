@"
# Plasma

A local-first, self-learning voice assistant.
Built on Windows with PyCharm, FastAPI, and a hybrid System 1 / System 2 architecture.

## Vision

Plasma is a personal AI assistant that:
- Runs locally by default (voice, intent routing, memory) — no cloud for 80% of requests
- Reaches for cloud LLMs (Claude, Groq) only for genuine reasoning work
- Learns continuously by rewriting its own skills as markdown files, gated by unit tests
- Keeps all user data on the user's machine, in human-readable files the user owns

## Architecture (high level)

- **System 1 (local):** wake word -> VAD -> local ASR -> intent router -> local SLM or direct action
- **System 2 (cloud):** escalated queries to Claude / Groq with PII redaction
- **Memory:** SQLite FTS5 + sqlite-vec, plus markdown skills and USER.md
- **Voice:** Whisper (local) in, Piper or Kokoro (local) out
- **Orchestration:** MCP clients + Windows automation (PowerShell, pywinauto)

## Roadmap

- [x] Step 1 — Project skeleton, GitHub, memory files
- [ ] Step 2 — FastAPI backend + WebSocket voice endpoint
- [ ] Step 3 — Local memory layer (SQLite FTS5)
- [ ] Step 4 — Local router (Ollama + small model)
- [ ] Step 5 — Local ASR (Whisper) pipeline
- [ ] Step 6 — Local TTS (Piper) pipeline
- [ ] Step 7 — Skill system (markdown + unit-test gate)
- [ ] Step 8 — USER.md + periodic nudge
- [ ] Step 9 — Cloud escalation with PII redaction + audit log
- [ ] Step 10 — Frontend (plasma orb UI)
- [ ] Step 11 — Windows system integration (PowerShell, calendar, mail)
- [ ] Step 12 — MCP client for external tools

## Tech stack

- Python 3.11+, FastAPI, uvicorn
- SQLite with FTS5 and sqlite-vec
- Ollama (local LLM runtime)
- Whisper (ASR), Piper (TTS)
- PyCharm, GitHub, Docker (later)

## License

Private. Author: Hocine Bahri.
"@ | Out-File -FilePath README.md -Encoding utf8