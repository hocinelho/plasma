# Plasma

**Local-first, self-learning voice assistant.**

Plasma is a desktop voice assistant that runs entirely on your hardware. It uses open-source speech recognition (Whisper), a local LLM (Ollama), and text-to-speech (Piper) to give you a private, fast, and extensible voice interface.

## Key Features

- **Voice-first** -- Push-to-talk or wake word ("Hey Jarvis") activation
- **Fully local** -- No cloud required. Your voice never leaves your machine.
- **Cloud optional** -- Connect to Gemini, OpenRouter, Cerebras, or Groq for faster/smarter replies
- **29 built-in skills** -- Weather, calendar, email, timers, Spotify, Wikipedia, translation, and more
- **German + English** -- Multilingual speech recognition and TTS with auto language detection
- **Self-learning memory** -- Plasma remembers facts about you across sessions
- **Speaker identification** -- Recognizes who is speaking and keeps per-user profiles
- **Extensible** -- Add new skills as simple Python files with triggers and a `run()` function
- **Mobile-friendly UI** -- Responsive web interface with tap-to-talk on phones
- **Analytics dashboard** -- Track skill usage, latency, and memory facts

## How It Works

1. You speak into your microphone (push-to-talk button or wake word)
2. Whisper transcribes your speech to text
3. The skill router checks for keyword matches against 29 skills
4. If no skill matches, the transcript goes to your LLM (local Ollama or cloud)
5. The reply is spoken back to you via Piper TTS
6. Facts are extracted and stored in a local SQLite database

## Quick Start

```bash
git clone https://github.com/hocinelho/plasma.git
cd plasma
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your preferences
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

See [Installation](installation.md) for detailed setup instructions.
