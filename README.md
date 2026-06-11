# Plasma

A local-first, self-learning voice assistant that runs entirely on your machine.

## What it does

Talk to Plasma like a person. It listens, understands, remembers, and speaks back — all locally, no cloud required.

- **31 built-in skills**: time, weather, calculator, timer, reminders, Wikipedia, translation, calendar, email, Spotify, volume control, screenshots, news, todos, voice notes, and more
- **Bilingual**: English and German with automatic language detection
- **Voice profiles**: "Remember my voice as Hocine" — Plasma recognizes who's speaking and keeps per-user memory
- **Self-learning memory**: remembers facts you tell it and builds a profile of your preferences
- **Privacy-first**: all data stays on your machine in human-readable files

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/hocinelho/plasma.git
cd plasma
pip install -r requirements.txt

# 2. Start Ollama (download from ollama.ai)
ollama serve
ollama pull mistral

# 3. Launch Plasma
python run_plasma.py
```

Open [http://localhost:8000](http://localhost:8000) — hold SPACE to talk.

Visit [http://localhost:8000/setup](http://localhost:8000/setup) to verify all components are working.

## Architecture

```
Browser mic → WebM → FFmpeg → Whisper ASR → Skill router → Ollama LLM → Piper TTS → Browser
                                                ↕
                                      SQLite memory (FTS5)
```

- **System 1 (local)**: wake word → VAD → Whisper ASR → intent router → skill or local LLM
- **System 2 (cloud)**: optional escalation to cloud LLMs (Gemini, OpenRouter) with PII redaction
- **Memory**: SQLite FTS5 + markdown skills + USER.md per-person profiles
- **Voice**: Whisper (in), Piper (out), with German voice support

## Skills

| Category | Skills |
|----------|--------|
| **Info** | time, date, weather, 5-day forecast, Wikipedia, news headlines |
| **Productivity** | timer, reminders, calculator, unit converter, todos, voice notes |
| **Calendar** | view today's events, add events (Google Calendar + Outlook) |
| **Email** | unread count (Gmail + Outlook) |
| **Media** | Spotify control, volume control, screenshot |
| **System** | open apps, translate, jokes, settings control, update check |
| **Personal** | remember facts, recall memory, forget, voice profiles |

## Configuration

Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `mistral:latest` | Local LLM model |
| `WHISPER_MODEL` | `small.en` | ASR model (`small` for German) |
| `WHISPER_LANGUAGE` | `en` | `en`, `de`, or `auto` |
| `TTS_ENABLED` | `true` | Text-to-speech on/off |
| `CLOUD_API_KEY` | (empty) | Optional cloud LLM key |

See [docs/configuration.md](docs/configuration.md) for full reference.

## Windows Installer

Build a standalone `.exe` (no Python needed on target machine):

```bash
pip install pyinstaller
python scripts/build_installer.py
```

Output: `dist/Plasma/Plasma.exe` — just needs Ollama installed separately.

## Pages

| URL | Description |
|-----|-------------|
| `/` | Main voice assistant UI |
| `/setup` | First-run setup wizard |
| `/analytics` | Memory, skills stats, latency dashboard |

## Tech Stack

- Python 3.11+, FastAPI, uvicorn
- SQLite with FTS5
- Ollama (local LLM)
- faster-whisper (ASR), Piper (TTS)
- Google Calendar/Gmail API, Microsoft Graph API
- PyInstaller for distribution

## CI

GitHub Actions runs on every push: compile check + 280+ tests.

[![CI](https://github.com/hocinelho/plasma/actions/workflows/ci.yml/badge.svg)](https://github.com/hocinelho/plasma/actions/workflows/ci.yml)

## License

Private. Author: Hocine Bahri.
