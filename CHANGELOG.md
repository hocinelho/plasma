# Changelog

All notable changes to Plasma are documented in this file.

## [0.12.0] - 2026-06-11 (Sprint 15)

### Added
- **PA-64**: Voice-controlled settings -- switch Whisper model and language by voice ("switch to faster model", "speak German", "auto detect language")
- **PA-81**: Auto-update check against GitHub releases -- "check for updates" skill and `/api/version` endpoint
- **PA-83**: Public documentation site (GitHub Pages ready) -- installation guide, skills reference, configuration, architecture
- **PA-84**: Changelog generation from git history

### Changed
- Added `reload_model()` to voice pipeline for hot-swapping Whisper models at runtime
- Total skill count now 31 (29 existing + settings_control + update_check)

## [0.11.0] - Sprint 14

### Added
- **PA-82**: First-run setup wizard at `/setup` with component health checks, fix hints, and German voice download

## [0.10.0] - Sprint 12

### Added
- **PA-68**: Analytics API -- `/api/facts`, `/api/facts/{id}` (DELETE), fact browsing and deletion
- **PA-72**: Skill usage statistics -- `/api/skills/stats` endpoint with usage counts
- **PA-73**: Analytics & Memory dashboard -- `/analytics` page with latency charts, fact management, skill stats

## [0.9.0] - Sprint 11

### Added
- **PA-65**: Speaker identification using resemblyzer voice embeddings -- "remember my voice as <name>"
- **PA-66**: Per-user memory and USER.md files -- facts stored per speaker
- **PA-67**: Voice selection skill -- switch TTS voices by name, list available voices

## [0.8.0] - Sprint 10

### Added
- **PA-69**: Mobile-responsive UI -- fluid layout, touch-friendly button sizing
- **PA-70**: Tap-to-toggle recording on touch devices (no hold required)
- **PA-71**: High-contrast accessibility theme with persistent preference

## [0.7.0] - Sprint 9

### Added
- **PA-48**: German language support -- multilingual Whisper model, German TTS voice (Piper Thorsten)
- **PA-50**: Auto language detection (`WHISPER_LANGUAGE=auto`) with clamping to configured languages
- **PA-51**: German trigger phrases for all existing skills
- **PA-52**: Language-aware TTS -- automatic voice switching between English and German

## [0.6.0] - Sprint 8

### Added
- **PA-74**: System volume control skill (Windows)
- **PA-75**: Screenshot skill -- captures screen to Desktop
- **PA-76**: Spotify playback control -- play, pause, next, previous, current track
- **PA-77**: Spotify authentication flow
- **PA-34**: Wake word detection -- "Hey Jarvis" hands-free activation via WebSocket

### Fixed
- Voice notes/todo strip comma separator from speech-to-text

## [0.5.0] - Sprint 7

### Added
- **PA-60**: Voice notes skill -- save and read voice notes
- **PA-61**: Todo list skill -- voice-driven task management
- **PA-62**: News headlines skill -- BBC News RSS feed
- **PA-63**: 5-day weather forecast skill

## [0.4.0] - Sprint 6

### Added
- **PA-41**: Outlook calendar skill -- read today's events via Microsoft Graph
- **PA-42**: Outlook email count skill -- unread inbox count
- **PA-43**: Calendar event creation skill -- add events by voice

### Fixed
- Weather skill trigger conflict with calculator "what is"
- TLS certificate errors on corporate networks (truststore integration)

## [0.3.0] - Sprint 5

### Added
- **PA-57**: Wikipedia lookup skill -- one-sentence summaries
- **PA-58**: Translation skill -- translate phrases between languages
- **PA-59**: Reminder skill -- time-based reminders

### Fixed
- Skills registry log count and Wikipedia short-topic guard

## [0.2.0] - Sprint 4

### Added
- **PA-53**: Timer skill -- countdown timers with notification
- **PA-54**: Calculator skill -- natural language math expressions
- **PA-55**: Joke skill -- random jokes in English and German
- **PA-56**: Unit converter skill -- length, weight, temperature, volume

## [0.1.0] - Sprints 1-3

### Added
- Project skeleton with FastAPI backend
- SQLite memory store with FTS5 (conversations, facts, skills)
- Ollama router with `/chat` endpoint and conversation memory
- Voice pipeline: audio capture, VAD, Whisper transcription, FFmpeg decode
- Push-to-talk web UI with SPACE key shortcut
- Piper TTS with voice warmup
- Skill registry with auto-discovery and self-test gating
- Core skills: get_time, get_date, open_app, remember_this, what_do_you_remember, forget_this, weather
- USER.md auto-writer with fact-based profile generation
- Skill suggester with template-based generation
- Waveform visualization, conversation history with timestamps, status indicator
- Cloud LLM support (provider-agnostic) with Ollama fallback
- PII redactor module
- Audit logging for outbound cloud LLM calls
