# Configuration

All configuration is done through environment variables in a `.env` file at the project root. Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

## Local LLM (Ollama)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `mistral:latest` | Model for chat responses |

## Cloud LLM (Optional)

Plasma can use a cloud LLM (OpenAI-compatible API) for faster or smarter replies. It falls back to local Ollama if the cloud is unavailable.

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUD_API_KEY` | (empty) | API key. Leave blank for local-only mode. |
| `CLOUD_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | API base URL |
| `CLOUD_MODEL` | `gemini-2.0-flash` | Model name |

### Supported providers

| Provider | Base URL | Model | Free tier |
|----------|----------|-------|-----------|
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` | 1500 req/day |
| OpenRouter | `https://openrouter.ai/api/v1` | `moonshotai/kimi-k2.6:free` | 200 req/day |
| OpenRouter auto | `https://openrouter.ai/api/v1` | `openrouter/free` | 50 req/day |
| Cerebras | `https://api.cerebras.ai/v1` | `llama-3.3-70b` | 60K tok/min |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` | Paid |

## Speech Recognition (Whisper)

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL` | `small.en` | Model size. See options below. |
| `WHISPER_LANGUAGE` | `en` | `en`, `de`, or `auto` for auto-detection |
| `WHISPER_ALLOWED_LANGS` | `en,de` | Comma-separated languages for auto-detect clamping |

### Model options

| Model | Speed | Languages | Notes |
|-------|-------|-----------|-------|
| `tiny.en` | ~1s | English only | Fastest, least accurate |
| `base.en` | ~2s | English only | Good balance |
| `small.en` | ~3-5s | English only | Default, good accuracy |
| `medium.en` | ~8s | English only | Best for accents |
| `small` | ~3-5s | Multilingual | Required for German |
| `medium` | ~8s | Multilingual | Best multilingual accuracy |

## Text-to-Speech (Piper)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_ENABLED` | `true` | Enable/disable TTS |
| `TTS_VOICE_MODEL` | (empty) | Path to English Piper `.onnx` voice |
| `TTS_VOICE_DE` | (empty) | Path to German Piper `.onnx` voice |

## Wake Word

| Variable | Default | Description |
|----------|---------|-------------|
| `WAKE_WORD_ENABLED` | `false` | Enable hands-free "Hey Jarvis" detection |
| `WAKE_WORD_MODEL` | `hey_jarvis` | Pre-trained wake word model |
| `WAKE_WORD_THRESHOLD` | `0.5` | Detection sensitivity (0.1 = sensitive, 0.9 = strict) |

## Speaker Identification

| Variable | Default | Description |
|----------|---------|-------------|
| `SPEAKER_ID_ENABLED` | `true` | Enable voice profiles (requires `resemblyzer`) |
| `SPEAKER_THRESHOLD` | `0.70` | Cosine similarity threshold (0.5 = loose, 0.9 = strict) |

## Microsoft Graph (Outlook)

| Variable | Default | Description |
|----------|---------|-------------|
| `MS_CLIENT_ID` | (empty) | Azure app registration client ID |
| `MS_TENANT_ID` | `common` | Azure tenant (`common` for personal + work) |

Setup: Register an app at [portal.azure.com](https://portal.azure.com), then run `python scripts/ms_auth.py`.

## Spotify

| Variable | Default | Description |
|----------|---------|-------------|
| `SPOTIFY_CLIENT_ID` | (empty) | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | (empty) | Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:9090` | OAuth redirect URI |

## Networking

| Variable | Default | Description |
|----------|---------|-------------|
| `PLASMA_INSECURE_SSL` | `false` | Disable TLS verification (dev/corporate proxy workaround) |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `PLASMA_LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
