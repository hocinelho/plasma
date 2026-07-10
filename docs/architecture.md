# Architecture

## Overview

Plasma is a local-first voice assistant built with a Python backend (FastAPI) and a browser-based frontend. All processing happens on your machine by default, with optional cloud LLM fallback.

```
Browser (frontend)
    |
    | HTTP / WebSocket
    v
FastAPI (backend/main.py)
    |
    +-- Voice Pipeline (ASR)
    |       Whisper (faster-whisper) -- speech to text
    |
    +-- Skill Router (registry.py)
    |       29 built-in skills matched by keyword triggers
    |
    +-- LLM Chain (chat_service.py)
    |       Cloud LLM (Gemini/OpenRouter/etc.) --> Ollama (local fallback)
    |
    +-- Memory Store (SQLite)
    |       Conversations, facts, skill usage, request logs
    |
    +-- TTS (Piper)
    |       Text to speech with language-specific voices
    |
    +-- Wake Word (openWakeWord)
            "Hey Jarvis" hands-free activation
```

## Voice Pipeline

The voice pipeline processes audio in four stages:

1. **Audio capture**: Browser MediaRecorder captures audio as WebM/Opus
2. **Decode**: FFmpeg (bundled via imageio-ffmpeg) converts to 16 kHz mono PCM
3. **Transcribe**: faster-whisper processes the audio and returns text + detected language
4. **Post-process**: Silence rejection (RMS check), language clamping (auto-detect restricted to configured languages)

```
Browser mic --> WebM blob --> POST /voice/chat
    --> FFmpeg decode (16kHz mono)
    --> Silence check (RMS > 200)
    --> Whisper transcribe
    --> text + language
```

## Skill Routing

Skills are Python files in `backend/skills/` auto-loaded at startup. Each skill has:

- `META` dict with name, description, and trigger phrases
- `run(args)` function that returns a text response
- Optional `self_test()` function (must return True for the skill to load)

The router (`registry.py`) uses **longest-trigger-wins** matching: for each skill's triggers, it checks if the trigger appears in the lowercased utterance. The skill whose matching trigger is longest wins.

If no skill matches, the utterance goes to the LLM chain.

## LLM Fallback Chain

```
User utterance
    |
    v
Skill router --> match? --> Skill.run() --> response
    |
    | no match
    v
Cloud LLM (if CLOUD_API_KEY set)
    |
    | fails or not configured
    v
Ollama local LLM --> response
```

The system prompt includes known facts about the user and the identified speaker name. History is limited to the last 20 messages.

## Memory System

SQLite database at `.plasma/memory.sqlite` with these tables:

- **conversations**: Chat history (session_id, role, content, timestamp)
- **facts**: Extracted user facts (category, content, user, timestamp)
- **skills_meta**: Registered skills with usage counts
- **request_log**: Per-turn latency metrics (ASR, LLM, TTS, total)

Facts are categorized as: identity, preference, project, location, routine, relationship, interest, or general.

### USER.md Auto-Generation

Every 10 conversation turns, Plasma regenerates a USER.md file from stored facts. This file is injected into the LLM system prompt so Plasma remembers the user across sessions without re-reading the database each turn.

## Speaker Identification

When `resemblyzer` is installed, Plasma can identify who is speaking:

1. Audio PCM is passed to a voice embedding model (256-dim vector)
2. Cosine similarity compared against enrolled speaker profiles
3. If similarity exceeds `SPEAKER_THRESHOLD`, the speaker is identified
4. Per-speaker facts and USER.md files are maintained separately

Enrollment: say "remember my voice as YourName" while speaking.

## Frontend

Single-page web app served by FastAPI at `/`. Key features:

- Push-to-talk (hold button or SPACE key on desktop)
- Tap-to-toggle on mobile/touch devices
- Real-time waveform visualization during recording
- Conversation log with timestamps
- High-contrast accessibility mode
- Wake word WebSocket connection for hands-free activation

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/health` | Health + component status |
| GET | `/analytics` | Analytics dashboard |
| GET | `/setup` | First-run setup wizard |
| POST | `/chat` | Text chat |
| POST | `/voice/chat` | Voice chat (audio in, text + audio out) |
| GET | `/user/profile` | Current USER.md |
| POST | `/user/reflect` | Regenerate USER.md |
| GET | `/api/version` | Version and update info |
| GET | `/api/setup/status` | Setup check results |
| GET | `/api/facts` | Stored facts |
| DELETE | `/api/facts/{id}` | Delete a fact |
| GET | `/api/skills/stats` | Skill usage stats |
| GET | `/api/latency/{session}` | Per-turn latency |
| WS | `/ws/wake` | Wake word events |
