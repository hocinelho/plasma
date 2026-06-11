"""
Plasma - main backend entrypoint.

Endpoints:
- GET  /              — serve the web UI (frontend/index.html)
- GET  /health        — health + component status + Ollama/TTS probes
- POST /chat          — text chat: user message -> Ollama (with memory) -> reply
- POST /voice/chat    — voice chat: WebM/WAV audio -> Whisper -> /chat -> reply + Piper audio
- GET  /user/profile  — current USER.md contents
- POST /user/reflect  — regenerate USER.md from facts
- WS   /ws/wake       — wake word events (type: "wake") → browser auto-starts recording
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.core.config import config as plasma_config
from backend.modules.router.chat_service import handle_chat, get_memory
from backend.modules.router.ollama_client import health_check as ollama_health
from backend.modules.user.user_md import write_user_md, read_user_md
from backend.modules.voice.pipeline import transcribe_audio_bytes
from backend.modules.voice.tts import synthesize as tts_synthesize, health_check as tts_health
from backend.modules.skills.suggester import get_suggester
from backend.modules.voice.wake_monitor import wake_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("plasma")


# ---------------------------------------------------------------------------
# Lifespan: warm Ollama + Whisper + Piper on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Plasma backend starting up...")

    async def _warm_ollama():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                await client.post(
                    f"{plasma_config.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json={
                        "model": plasma_config.OLLAMA_MODEL,
                        "prompt": "",
                        "keep_alive": "30m",
                    },
                )
            log.info(f"Ollama model warmed: {plasma_config.OLLAMA_MODEL}")
        except Exception as e:
            log.warning(f"Ollama warmup skipped: {e}")

    async def _warm_whisper():
        try:
            from backend.modules.voice.pipeline import get_asr
            await asyncio.to_thread(get_asr)
            log.info("Whisper model warmed")
        except Exception as e:
            log.warning(f"Whisper warmup skipped: {e}")

    async def _warm_tts():
        try:
            from backend.modules.voice.tts import _load_voice
            if plasma_config.TTS_ENABLED:
                await asyncio.to_thread(_load_voice)
                log.info("Piper TTS voice warmed")
        except Exception as e:
            log.warning(f"Piper warmup skipped: {e}")

    asyncio.create_task(_warm_ollama())
    asyncio.create_task(_warm_whisper())
    asyncio.create_task(_warm_tts())
    await wake_monitor.start()

    yield

    await wake_monitor.stop()
    log.info("Plasma backend shutting down...")


app = FastAPI(
    title="Plasma",
    description="Local-first, self-learning voice assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: refresh USER.md every N turns
# ---------------------------------------------------------------------------
def _maybe_refresh_user_md(session_id: str, every_n_turns: int = 10) -> None:
    try:
        msgs = get_memory().get_conversation(session_id, limit=1000)
        if msgs and len(msgs) % every_n_turns == 0:
            asyncio.create_task(asyncio.to_thread(write_user_md))
            log.info(
                f"USER.md refresh scheduled (session={session_id}, turns={len(msgs)})"
            )
    except Exception as e:
        log.warning(f"USER.md auto-refresh failed: {e}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    """Serve the web UI (push-to-talk page)."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"name": "Plasma", "version": "0.1.0", "status": "online"}


@app.get("/analytics")
async def analytics_page():
    """Serve the Analytics & Memory dashboard."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "analytics.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"error": "analytics.html not found"}, status_code=404)


@app.get("/setup")
async def setup_page():
    """Serve the first-run setup wizard (PA-82)."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "setup.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"error": "setup.html not found"}, status_code=404)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    ollama = ollama_health()
    tts = tts_health()
    return {
        "status": "ok",
        "config": plasma_config.summary(),
        "components": {
            "backend": "ok",
            "memory": "ok",
            "router": "ok" if ollama.get("reachable") else "ollama_unreachable",
            "asr": "ok",
            "tts": "ok" if tts.get("loaded") else "not_loaded",
        },
        "ollama": ollama,
        "tts": tts,
    }


# ---------------------------------------------------------------------------
# Version / update check (PA-81)
# ---------------------------------------------------------------------------
@app.get("/api/version")
async def api_version():
    """Return current version and check for updates on GitHub."""
    import asyncio
    from backend.skills.update_check import get_version_info
    info = await asyncio.to_thread(get_version_info)
    return info


# ---------------------------------------------------------------------------
# Setup wizard (PA-82) — guided first-run checks + fixes
# ---------------------------------------------------------------------------
def _check(fn):
    """Run a single setup check, never letting an exception escape.

    Each check function returns a dict (without ``id``/``label``/``category``,
    which are filled in by the caller). On any exception the check is marked
    failed with the error in ``detail`` so one broken probe never 500s the
    whole status endpoint.
    """
    try:
        return fn()
    except Exception as e:
        return {"ok": False, "detail": f"check failed: {e}", "fix": None}


def _gather_setup_checks() -> list[dict]:
    """Build the ordered list of setup checks with pass/fail + fix hints."""

    def whisper_model():
        model = (plasma_config.WHISPER_MODEL or "").strip()
        if not model:
            return {
                "ok": False,
                "detail": "WHISPER_MODEL not set",
                "fix": "Set WHISPER_MODEL in your .env (e.g. small.en or small).",
            }
        multilingual = ".en" not in model
        kind = "multilingual" if multilingual else "English-only"
        return {
            "ok": True,
            "detail": f"{model} ({kind}) — downloads automatically on first use",
            "fix": None,
        }

    def vad_model():
        # Plasma's VAD uses the `silero-vad` pip package (weights bundled in the
        # package), not a standalone .onnx file. Report based on importability.
        try:
            import silero_vad  # noqa: F401
            return {"ok": True, "detail": "silero-vad package installed", "fix": None}
        except Exception:
            return {
                "ok": False,
                "detail": "silero-vad package not importable",
                "fix": "Install voice deps: pip install -r requirements.txt",
            }

    def tts_voice():
        from backend.modules.voice.tts import health_check as _tts_health
        h = _tts_health()
        if not h.get("enabled", True):
            return {"ok": False, "detail": "TTS disabled (TTS_ENABLED=false)", "fix": "Set TTS_ENABLED=true in .env."}
        if h.get("loaded"):
            return {"ok": True, "detail": h.get("model") or "loaded", "fix": None}
        return {
            "ok": False,
            "detail": h.get("error") or "voice model not loaded",
            "fix": "Set TTS_VOICE_MODEL in .env to a Piper .onnx voice in voices/.",
        }

    def ollama_running():
        h = ollama_health()
        if h.get("reachable"):
            return {"ok": True, "detail": plasma_config.OLLAMA_BASE_URL, "fix": None}
        return {
            "ok": False,
            "detail": h.get("error") or "not reachable",
            "fix": "Start Ollama: open a terminal and run 'ollama serve'.",
        }

    def ollama_model():
        h = ollama_health()
        model = plasma_config.OLLAMA_MODEL
        if not h.get("reachable"):
            return {
                "ok": False,
                "detail": "can't check — Ollama not reachable",
                "fix": f"Start Ollama, then run: ollama pull {model.split(':')[0]}",
            }
        if "model_present" in h:
            if h.get("model_present"):
                return {"ok": True, "detail": model, "fix": None}
            return {
                "ok": False,
                "detail": f"{model} not pulled",
                "fix": f"Run: ollama pull {model.split(':')[0]}",
            }
        # Best effort: reachable but model list unavailable
        return {"ok": True, "detail": f"{model} (assumed — model list unavailable)", "fix": None}

    def german_voice():
        from backend.modules.voice.tts import VOICES_DIR, _resolve_model
        # Configured German voice present?
        if plasma_config.TTS_VOICE_DE:
            p = _resolve_model(plasma_config.TTS_VOICE_DE)
            if p.exists():
                return {"ok": True, "detail": p.name, "fix": None, "downloadable": "de_voice"}
        # Any de_*.onnx already in voices/?
        if VOICES_DIR.exists():
            de_files = sorted(VOICES_DIR.glob("de_*.onnx"))
            if de_files:
                return {"ok": True, "detail": de_files[0].name, "fix": None, "downloadable": "de_voice"}
        return {
            "ok": False,
            "detail": "not installed",
            "fix": "Click Download below to fetch the German Thorsten voice.",
            "downloadable": "de_voice",
        }

    def speaker_id():
        from backend.modules.voice import speaker_id as _sid
        if _sid.is_available():
            return {"ok": True, "detail": "resemblyzer installed", "fix": None}
        return {
            "ok": False,
            "detail": "resemblyzer not installed (single-user mode)",
            "fix": "pip install resemblyzer",
        }

    def cloud_llm():
        configured = bool((plasma_config.CLOUD_API_KEY or "").strip())
        return {
            "ok": True,
            "detail": "configured" if configured else "not configured — using local Ollama only",
            "fix": None,
        }

    specs = [
        ("whisper_model", "Whisper speech model", "required", whisper_model),
        ("vad_model", "Voice activity detection model", "required", vad_model),
        ("tts_voice", "English TTS voice", "required", tts_voice),
        ("ollama_running", "Ollama server", "required", ollama_running),
        ("ollama_model", "Ollama model available", "required", ollama_model),
        ("german_voice", "German TTS voice (optional)", "optional", german_voice),
        ("speaker_id", "Voice profiles / speaker ID (optional)", "optional", speaker_id),
        ("cloud_llm", "Cloud LLM (optional)", "optional", cloud_llm),
    ]

    checks = []
    for cid, label, category, fn in specs:
        result = _check(fn)
        checks.append({
            "id": cid,
            "label": label,
            "category": category,
            "ok": bool(result.get("ok")),
            "detail": result.get("detail"),
            "fix": result.get("fix"),
            "downloadable": result.get("downloadable"),
        })
    return checks


@app.get("/api/setup/status")
async def setup_status():
    """Run every setup check and report pass/fail + fix instructions (PA-82)."""
    checks = await asyncio.to_thread(_gather_setup_checks)

    required = [c for c in checks if c["category"] == "required"]
    optional = [c for c in checks if c["category"] == "optional"]
    required_ok = sum(1 for c in required if c["ok"])
    optional_ok = sum(1 for c in optional if c["ok"])

    return {
        "checks": checks,
        "summary": {
            "required_ok": required_ok,
            "required_total": len(required),
            "optional_ok": optional_ok,
            "optional_total": len(optional),
            "ready": required_ok == len(required),
        },
    }


@app.post("/api/setup/download/de_voice")
async def setup_download_de_voice():
    """Download the German Piper voice (PA-82). May take 30-120s."""
    try:
        from scripts.download_de_voice import download_de_voice
        path = await asyncio.to_thread(download_de_voice, False)
        return {"ok": True, "path": str(path)}
    except Exception as e:
        log.warning(f"German voice download failed: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Text chat
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Text chat: user message -> Ollama (with memory) -> reply."""
    reply = await asyncio.to_thread(handle_chat, req.session_id, req.message)
    _maybe_refresh_user_md(req.session_id)
    return ChatResponse(session_id=req.session_id, reply=reply)


# ---------------------------------------------------------------------------
# Voice chat (browser push-to-talk, with TTS)
# ---------------------------------------------------------------------------
@app.post("/voice/chat")
async def voice_chat(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
):
    """
    Full voice round-trip:
    1. Receive recorded audio blob from the browser (WebM/WAV)
    2. Transcribe with Whisper
    3. Pass transcript through existing /chat logic (Ollama + memory)
    4. Synthesize the reply to audio with Piper
    5. Return transcript, text reply, and base64-encoded WAV
    """
    t_start = time.monotonic()
    data = await audio.read()
    log.info(f"Received audio blob: {len(data)} bytes, session={session_id}")

    asr_t0 = time.monotonic()
    asr_result = await asyncio.to_thread(transcribe_audio_bytes, data)
    asr_ms = (time.monotonic() - asr_t0) * 1000.0
    transcript = asr_result.get("text", "").strip()
    pcm_audio = asr_result.pop("_audio", None)  # PA-65: decoded PCM for speaker ID

    if not transcript:
        return {
            "session_id": session_id,
            "transcript": "",
            "reply": "(I couldn't hear anything.)",
            "error": asr_result.get("error"),
            "audio_b64": None,
        }

    detected_language = asr_result.get("language", "en")

    # PA-65: voice enrollment — "remember my voice as <name>".
    # Handled BEFORE skill routing because it needs the raw audio.
    from backend.modules.voice import speaker_id
    enroll_name = speaker_id.parse_enroll_command(transcript)
    llm_t0 = time.monotonic()
    if enroll_name:
        reply = await asyncio.to_thread(speaker_id.enroll, enroll_name, pcm_audio)
        speaker = enroll_name if enroll_name in speaker_id.list_speakers() else None
    else:
        # PA-65: identify who is speaking (no-op when resemblyzer missing)
        speaker, _score = await asyncio.to_thread(speaker_id.identify, pcm_audio)
        reply = await asyncio.to_thread(
            handle_chat, session_id, transcript, detected_language, speaker
        )
        _maybe_refresh_user_md(session_id)
    llm_ms = (time.monotonic() - llm_t0) * 1000.0

    # Synthesize reply audio with Piper (fail gracefully — still return text)
    audio_b64 = None
    tts_ms = 0.0
    if plasma_config.TTS_ENABLED:
        try:
            tts_t0 = time.monotonic()
            wav_bytes = await asyncio.to_thread(tts_synthesize, reply, detected_language)
            tts_ms = (time.monotonic() - tts_t0) * 1000.0
            if wav_bytes:
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
                log.info(f"TTS audio encoded: {len(audio_b64)} b64 chars")
        except Exception as e:
            log.warning(f"TTS synthesis failed: {e}")

    total_ms = (time.monotonic() - t_start) * 1000.0

    # Log per-turn latency to request_log
    try:
        memory = get_memory()
        turn_num = len(memory.get_conversation(session_id, limit=1000))
        await asyncio.to_thread(
            memory.log_request,
            session_id, turn_num,
            asr_ms, llm_ms, tts_ms, total_ms, None,
        )
    except Exception as e:
        log.warning(f"Failed to log request latency: {e}")

    return {
        "session_id": session_id,
        "transcript": transcript,
        "reply": reply,
        "speaker": speaker,
        "asr_latency_s": asr_result.get("latency"),
        "asr_ms": asr_ms,
        "llm_ms": llm_ms,
        "tts_ms": tts_ms,
        "total_ms": total_ms,
        "audio_b64": audio_b64,
    }


# ---------------------------------------------------------------------------
# USER.md (auto-generated user profile)
# ---------------------------------------------------------------------------
@app.post("/user/reflect")
async def user_reflect():
    """Regenerate USER.md's auto block from the current facts in memory."""
    path = await asyncio.to_thread(write_user_md)
    return {
        "status": "ok",
        "path": str(path),
        "content": read_user_md(),
    }


@app.get("/user/profile")
async def user_profile():
    """Return the current USER.md contents."""
    return {"content": read_user_md() or "(USER.md does not exist yet)"}

# ---------------------------------------------------------------------------
# Skill proposals
# ---------------------------------------------------------------------------
@app.get("/skills/proposals")
async def get_skill_proposals():
    """List all skill proposals (pending, approved, rejected)."""
    return {"proposals": get_suggester().list_proposals()}


@app.post("/skills/proposals/approve/{name}")
async def approve_skill_proposal(name: str):
    return {"result": get_suggester().approve(name)}


@app.post("/skills/proposals/reject/{name}")
async def reject_skill_proposal(name: str):
    return {"result": get_suggester().reject(name)}


# ---------------------------------------------------------------------------
# Analytics API (PA-68, PA-72, PA-73)
# ---------------------------------------------------------------------------
@app.get("/api/facts")
async def api_get_facts(
    category: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
    limit: int = Query(default=500),
):
    """Return all stored facts as JSON."""
    memory = get_memory()
    if category:
        facts = await asyncio.to_thread(memory.get_facts, category, limit)
    else:
        facts = await asyncio.to_thread(memory.get_facts_all, limit)
    return {"facts": facts}


@app.delete("/api/facts/{fact_id}")
async def api_delete_fact(fact_id: int):
    """Delete a fact by ID."""
    memory = get_memory()
    deleted = await asyncio.to_thread(memory.delete_fact, fact_id)
    if deleted:
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "Fact not found"}, status_code=404)


@app.get("/api/skills/stats")
async def api_skills_stats():
    """Return skills list with usage counts, sorted by usage_count descending."""
    memory = get_memory()
    skills = await asyncio.to_thread(memory.get_skills_meta)
    return {"skills": skills}


@app.get("/api/latency/{session_id}")
async def api_latency(session_id: str):
    """Return per-turn latency history for a session."""
    memory = get_memory()
    rows = await asyncio.to_thread(memory.get_request_log, session_id)
    return {"session_id": session_id, "latency": rows}


# ---------------------------------------------------------------------------
# WebSocket — wake word broadcast (PA-34)
# ---------------------------------------------------------------------------
@app.websocket("/ws/wake")
async def websocket_wake(ws: WebSocket):
    """
    Browser connects here to receive wake word events.
    On detection the server sends: {"type": "wake", "score": float}
    The browser auto-starts the recording flow on receipt.
    """
    await ws.accept()
    wake_monitor.add_client(ws)
    log.info("Wake WS client connected")
    try:
        while True:
            # Keep the connection open; we don't expect messages from browser
            await ws.receive_text()
    except WebSocketDisconnect:
        wake_monitor.remove_client(ws)
        log.info("Wake WS client disconnected")