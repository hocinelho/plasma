# Running Plasma across several machines

Three things can live on different hardware:

| Piece | Where it can run | Why move it |
|---|---|---|
| **The LLM** (Ollama) | any PC on your network | a bigger, better model — and it stops competing with the UI for your laptop's CPU |
| **The model files** | any disk, internal or external | models are 4–40 GB each |
| **The UI** | any browser on the network, incl. your phone | use Plasma from the sofa |

The good news: none of this needs new code. Plasma already routes every LLM
call through `OLLAMA_BASE_URL`, and already has an HTTPS launcher for phones.

---

## 1. The other PC as the model server

**On the strong PC** (the one that will run the model):

```powershell
# Accept connections from the network, not just from itself
setx OLLAMA_HOST "0.0.0.0:11434"

# Optional: keep the models on a different disk
setx OLLAMA_MODELS "D:\ollama-models"

# Restart Ollama, then pull a model worth the hardware
ollama pull qwen2.5:14b
```

Allow it through the firewall once:

```powershell
New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound `
  -LocalPort 11434 -Protocol TCP -Action Allow
```

Find that PC's LAN address with `ipconfig` (something like `192.168.1.50`).

**On the Plasma PC**, edit `.env`:

```
OLLAMA_BASE_URL=http://192.168.1.50:11434
OLLAMA_MODEL=qwen2.5:14b
```

Restart Plasma. Check it worked:

```powershell
curl http://192.168.1.50:11434/api/tags
```

That is the whole change. Whisper and Piper still run locally — they are
small and want to be near the microphone.

### Which model?

The local model is the reason replies take 20–45 s today. Roughly, on a PC
with a decent GPU:

| Model | Size | Character |
|---|---|---|
| `llama3.2:3b`, `qwen2.5:3b` | ~2 GB | fast, noticeably simpler answers |
| `mistral:latest` | ~4 GB | current default |
| `qwen2.5:14b` | ~9 GB | much better reasoning, needs ~12 GB VRAM |
| `llama3.1:70b` | ~40 GB | excellent, needs a serious GPU |

**Speed comes from the GPU, not the disk.** A model on a fast SSD but running
on CPU is still slow; the same model in VRAM is many times faster. Check the
other PC's graphics card before picking a size.

---

## 2. Models on another disk

Set `OLLAMA_MODELS` (above) to any path — an internal drive, an external SSD,
or a NAS mount. Ollama reads the weights from there.

A caveat worth knowing: the model is **read into RAM/VRAM at load time**, so
disk speed affects how long the *first* request after a restart takes, not
the speed of each reply. An external USB drive is fine; a network share is
tolerable but makes that first load slow.

---

## 3. Using Plasma from your phone

Already supported:

```powershell
python serve_phone.py
```

It generates a self-signed certificate with your LAN IP baked in and serves
over HTTPS, which phones require before they will allow microphone or camera
access. Open the printed `https://192.168.x.x:8443` on the phone (same
Wi-Fi) and accept the certificate warning once.

The phone is a **client**: the mic and the 3D avatar run in its browser,
while ASR, the LLM and TTS run on the PCs. That is the right split — a phone
cannot host a 9 GB model, but it renders the avatar comfortably.

---

## Putting it together

```
Phone (browser)  ── https ──►  Plasma PC          ── http ──►  Strong PC
  mic, avatar                   Whisper, Piper                  Ollama + model
                                skills, memory                  (models on D:\)
```

Everything stays on your own network — no cloud, no accounts, which is the
point of Plasma being local-first.

## If something doesn't work

- `curl http://<ip>:11434/api/tags` from the Plasma PC — no answer means the
  firewall rule or `OLLAMA_HOST` is missing.
- `OLLAMA_HOST` must be `0.0.0.0:11434`, not `localhost:11434`; the default
  only listens to the machine itself.
- On Windows, `setx` only applies to **new** processes — restart Ollama (and
  the terminal) after setting it.
- Plasma's `/setup` page shows which model it is talking to and whether the
  call succeeded.
