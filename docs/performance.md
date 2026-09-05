# Making her fast

Every reply costs the sum of three stages, and Plasma already measures all
three. Guessing which one is slow is wasted effort — go and look first.

## 1. Find out where the time actually goes

Open **`/analytics`**. Every turn is logged with `asr_ms`, `llm_ms`, `tts_ms`
and `total_ms`. The same numbers come back in the JSON of every `/voice/chat`
call, and `GET /api/latency?session_id=default` gives you the history.

Rough guide to reading it:

| What dominates | What it means | Go to |
|---|---|---|
| `asr_ms` | Whisper is too big for the machine | §2 |
| `llm_ms` | the model is too big, or it unloaded | §3 |
| `tts_ms` | she is simply saying too much | §4 |
| all three small, still feels slow | nothing plays until *all* finish | §5 |

## 2. Speech recognition (`asr_ms`)

`WHISPER_MODEL` in `.env`. Each rung up roughly doubles the time:

```
tiny.en   ~1s      base.en  ~2s      small.en  ~3-5s      medium.en  ~8s
```

German or mixed speech needs the multilingual variants (`small`, `medium` —
no `.en`). If you only ever speak English, the `.en` models are both faster
and more accurate at the same size.

Setting `WHISPER_LANGUAGE=en` (or `de`) instead of `auto` removes a detection
pass and stops short phrases being mis-heard as another language.

## 3. The model (`llm_ms`)

**First, check it is not reloading.** Ollama unloads an idle model after five
minutes. Plasma now sends `keep_alive` on every request
(`OLLAMA_KEEP_ALIVE=30m`, `-1` for forever), but if you see one slow reply
after a break and fast ones after it, that is what you are looking at.

**Then pick the right size.** For a voice assistant, time-to-first-token
matters far more than benchmark scores. Nobody enjoys a brilliant answer that
arrives eight seconds late.

### Local models

| Model | Size | Notes |
|---|---|---|
| `qwen3:30b-a3b` | ~18 GB | **Best pick if you have ~24 GB RAM.** Mixture-of-experts: 30B total, ~3B active per token, so it answers like a big model at small-model speed. |
| `qwen3:14b` | ~9 GB | Dense; good quality, noticeably slower than the MoE above. |
| `qwen3:8b` / `qwen3:4b` | 5 / 2.5 GB | For modest laptops. |
| `mistral:latest` | ~4 GB | The current default. Fine, ageing. |

Avoid `deepseek-r1` and other **reasoning** models here. They emit a long
visible chain of thought before answering — excellent for maths, terrible when
the answer has to be spoken.

A GPU matters more than anything else in this table. On CPU only, stay at 8B
or below; with 24 GB of VRAM, `qwen3:30b-a3b` is genuinely quick.

### Frontier models, via the cloud

Kimi K2 and GLM-4.6 cannot run on a laptop — they are ~1T and ~355B parameter
mixture-of-experts models and need a server rack. They are reachable through
OpenRouter, and Plasma already supports this: it tries the cloud first and
falls back to Ollama automatically, with PII redaction and an audit log in
between.

```ini
CLOUD_PROVIDER=openai
CLOUD_BASE_URL=https://openrouter.ai/api/v1
CLOUD_API_KEY=sk-or-...
CLOUD_MODEL=moonshotai/kimi-k2.6:free    # or z-ai/glm-4.6
```

This is usually **faster** than a local model as well as smarter — a hosted
model answers in about a second, which a 14B on a laptop CPU will not match.
The trade is that what you say leaves the house, so it is off by default.
`CLOUD_CHAT_ENABLED=false` keeps chat local while still using the key for
vision.

### Another PC in the house

Point `OLLAMA_BASE_URL` at it and run the big model there. No code changes.
See [distributed-setup.md](distributed-setup.md).

## 4. Speech (`tts_ms`)

Piper synthesizes in roughly real time, so `tts_ms` is mostly a function of
**how much she says**. `OLLAMA_NUM_PREDICT=160` caps replies at a few
sentences, which cuts both generation and speech time at once. Lower it to
~96 if you want her terser still.

This is the cheapest speed setting in the whole file and the one people forget.

## 5. The part that is still slow by design

Even with every stage fast, nothing is heard until **all** of them finish:
Whisper transcribes, the model writes the whole reply, Piper renders the whole
reply, and only then does audio reach the browser.

So time-to-first-sound = `asr + llm(entire reply) + tts(entire reply)`.

The fix is to synthesize sentence by sentence and start playing the first one
while the rest is still being written, which would make time-to-first-sound
`asr + llm(first sentence) + tts(first sentence)` — typically 1–2s instead of
6–12s. `chat_first_sentence()` in `ollama_client.py` already streams tokens
from Ollama; what is missing is chunked synthesis and a streaming response to
the browser. **This is not built yet** and is the largest remaining win.

It is deliberately parked until the company server is available (agreed
2026-08-27) — see the PARKED section of [`../HANDOFF.md`](../HANDOFF.md) for
the design and what it touches.

`CHAT_FIRST_SENTENCE_ONLY=true` is a blunt version of it available today: she
answers with only her first sentence. It is fast and it truncates real
answers, which is why it is off by default.

## Quick checklist

```ini
OLLAMA_KEEP_ALIVE=30m        # stop the model unloading between questions
OLLAMA_NUM_PREDICT=160       # stop her rambling — saves twice over
WHISPER_MODEL=base.en        # drop a rung if asr_ms dominates
WHISPER_LANGUAGE=en          # or de — anything but auto
OLLAMA_MODEL=qwen3:30b-a3b   # if you have the RAM
```

Then look at `/analytics` again and see what moved.
