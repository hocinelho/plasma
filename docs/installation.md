# Installation

## Requirements

- Python 3.11 or newer
- [Ollama](https://ollama.ai/) for local LLM inference
- A microphone for voice input
- FFmpeg (bundled via `imageio-ffmpeg`, no manual install needed)

## Step-by-Step Setup

### 1. Clone the repository

```bash
git clone https://github.com/hocinelho/plasma.git
cd plasma
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Windows (cmd)
.\.venv\Scripts\activate.bat
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, Whisper (faster-whisper), Piper TTS, httpx, and all other dependencies.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your preferred settings. The key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `mistral:latest` | Which Ollama model to use |
| `WHISPER_MODEL` | `small.en` | Whisper model size (`tiny.en`, `base.en`, `small.en`, `medium.en`, `small`, `medium`) |
| `WHISPER_LANGUAGE` | `en` | `en`, `de`, or `auto` for auto-detection |
| `TTS_ENABLED` | `true` | Enable/disable text-to-speech |
| `CLOUD_API_KEY` | (empty) | Optional cloud LLM API key |

See [Configuration](configuration.md) for the full list.

### 5. Install and start Ollama

Download Ollama from [ollama.ai](https://ollama.ai/) and install it.

```bash
# Start the Ollama server
ollama serve

# In another terminal, pull a model
ollama pull mistral
```

### 6. Run Plasma

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser. The first run will download the Whisper model (~500 MB for `small.en`), which takes a few minutes.

### 7. First-run setup wizard

Visit [http://localhost:8000/setup](http://localhost:8000/setup) to verify all components are working. The wizard checks:

- Whisper model loaded
- Ollama server running and model pulled
- TTS voice available
- Optional: German voice, speaker ID, cloud LLM

## Windows-Specific Notes

- **Microphone access**: Windows may prompt for microphone permission in your browser. Allow it.
- **Ollama**: Download the Windows installer from [ollama.ai](https://ollama.ai/). It runs as a background service.
- **Corporate networks**: If you see TLS/certificate errors, Plasma uses `truststore` to handle corporate proxy certificates automatically. If issues persist, set `PLASMA_INSECURE_SSL=true` in `.env` (development only).
- **App launching**: The `open_app` skill supports Windows applications (Notepad, Calculator, Chrome, Edge, Outlook, etc.)

## Optional Features

### German language support

```bash
# Set multilingual model in .env
WHISPER_MODEL=small
WHISPER_LANGUAGE=auto

# Download German TTS voice
python scripts/download_de_voice.py
```

### Speaker identification

```bash
pip install resemblyzer
```

Then say "Remember my voice as YourName" to enroll.

### Cloud LLM (faster replies)

Add a cloud API key to `.env` for faster/smarter replies. Plasma falls back to local Ollama if the cloud is unavailable. See `.env.example` for provider options (Gemini, OpenRouter, Cerebras, Groq).
