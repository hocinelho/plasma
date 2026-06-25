# Vision / Locate — Work Log & Status

> Living status for the camera + "find my X" (LocateAnything) work on
> branch `claude/enhance-plasma-project-cOZli`. Update as bugs close.

_Last updated: 2026-06-25_

---

## Goal

Make Plasma **see through the camera** and answer "find my keys" / "where is my phone":

- Work **smoothly on the PC now**, and on **phones/laptops in the future**
  (phones connect to Plasma's browser UI — all vision runs server-side).
- **No performance loss** — must not freeze the machine.
- Recognise objects by natural language (open-vocabulary).

---

## Architecture — 3-tier vision backend

Tried in priority order; each tier falls through to the next on any failure:

| Tier | Backend | Speed | Install | Notes |
|------|---------|-------|---------|-------|
| 1 | **Cloud vision LLM** (Gemini / OpenRouter) | sub-second | none (uses `CLOUD_API_KEY`) | Needs internet + working key |
| 2 | **Ollama moondream** | fast on CPU | `ollama pull moondream` (~1.9 GB) | **Offline. Current working tier.** |
| 3 | **locate-anything.cpp CLI** | 5–70 s on CPU | 6 GB GGUF + C++ build | Heavy; for power users / GPU |

Config lives in `backend/core/config.py` (`LOCATE_*` vars). The skill is
`backend/skills/locate.py`. Camera capture is `backend/modules/vision/capture.py`.

**Recommended setup (offline, reliable):** blank `CLOUD_API_KEY`, use
moondream (tier 2) + local `mistral` for chat. No cloud dependency, no API keys
to break, phones just open the PC's browser URL.

---

## ✅ Fixes shipped (all pushed to the branch)

| # | Fix | Commit |
|---|-----|--------|
| 1 | 3-tier vision backend (cloud → Ollama → CLI), tier cascade on failure | `60bdaf1`, `b4fcdbb` |
| 2 | OpenRouter URL normalization + 404 auto-retry with `CLOUD_MODEL` | `3333e4c`, `058e0b1` |
| 3 | MUAPI image-gen slug fix (`flux-schnell-image`; bare slug 404s) | `c3a6bcd` |
| 4 | Robust webcam capture — DirectShow on Windows, warmup + retry frames | `b5690d9` |
| 5 | Response polish — strip quotes, wrap bare phrases into natural sentences | `49e239f` |
| 6 | Reduce hallucination — simpler prompt + Python-side response parser | `466d6c3`, `201c795` |
| 7 | Wake word debounce (N consecutive frames) + fixed misleading log | `82cf75e` |
| 8 | Empty-moondream retry + black-frame detection + image-size logging | `2f64257` |
| 9 | Ultra-short moondream prompt (`"Where is the {obj}?"`) + expanded not-found vocab + 3 retries | `09d8725` |

---

## ✅ Confirmed working

- Voice → ASR (faster-whisper) → LLM → TTS (Piper) pipeline.
- **Camera + moondream located a real object** ("find my key" → "near the door").
- Fully offline path (local `mistral` chat + moondream vision).

---

## 🔧 Open bugs / needs re-test

| Bug | Status | Action needed |
|-----|--------|---------------|
| moondream returns empty response | **Fixed** — root cause was over-complex prompt. Now uses `"Where is the {obj}?"` (moondream native format). | Restart + try again; image log should be followed by a real answer |
| Wake word false fires ("hello hocine" unprompted) | Debounce shipped — **re-test** | Set `WAKE_WORD_THRESHOLD=0.6`, `WAKE_WORD_TRIGGER_FRAMES=3` |
| OpenRouter every model returns 404 | **Not a code bug** — account/key issue | Use local models (recommended) or fix the OpenRouter key |

### Diagnostic: the image-size log line

After `git pull` + restart, "find my keys" prints:

```
locate: captured 640x480 image → /tmp/xxx.jpg (45.2 KB)
```

| Log shows | Meaning |
|-----------|---------|
| `< 1 KB` | Camera image is black — webcam slow/blocked by another app |
| `30+ KB` | Image is real — any failure is the vision model, not the camera |
| `Camera not available` (no size log) | Camera device isn't opening at all |

---

## .env reference (recommended offline setup)

```ini
# Go fully local — no cloud round-trips, no 404 delays
CLOUD_API_KEY=

# Local chat
OLLAMA_MODEL=mistral:latest

# Local vision (tier 2)
LOCATE_VISION_OLLAMA_MODEL=moondream

# Wake word tuning (stop false triggers)
WAKE_WORD_THRESHOLD=0.6
WAKE_WORD_TRIGGER_FRAMES=3
```

If accuracy isn't enough, swap to a bigger local vision model — no code change:

```ini
LOCATE_VISION_OLLAMA_MODEL=llama3.2-vision   # or llava:13b
```

---

## 📋 Not started (next features)

- **Phone camera** — stream the phone's own camera to the server (browser
  `getUserMedia`) instead of only the PC webcam.
- **Talking avatar** — animated Plasma icon with lip-sync while speaking.
- **Demo video** for the README (PA-86).

---

## Key files

| File | Responsibility |
|------|----------------|
| `backend/skills/locate.py` | The "find my X" skill, 3-tier logic, response parsing |
| `backend/modules/vision/capture.py` | Webcam capture (DirectShow + warmup/retry) |
| `backend/core/config.py` | All `LOCATE_*`, `MUAPI_*`, `WAKE_WORD_*` config vars |
| `backend/modules/voice/wake_word.py` | Wake-word detector + consecutive-frame debounce |
| `backend/modules/voice/wake_monitor.py` | Mic → detector → WebSocket broadcast |
| `tests/test_locate_and_imagegen.py` | Locate + image-gen tests |
| `tests/test_vision_skill.py` | Camera capture tests |
| `tests/test_pa89_wake_word.py` | Wake-word + debounce tests |
