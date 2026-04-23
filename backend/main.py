"""
Plasma - main backend entrypoint.

Endpoints:
- GET  /          — serve the web UI (frontend/index.html)
- GET  /health    — health + component status + Ollama/TTS probes
- POST /chat      — text chat: user message -> Ollama (with memory) -> reply
- POST /voice/chat — voice chat: WebM/WAV audio -> Whisper -> /chat -> reply + Piper audio
- WS   /ws        — reserved for future streaming use
"""
from __future__ import annotations

import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.config import config as plasma_config
from backend.modules.router.chat_service import handle_chat
from backend.modules.router.ollama_client import health_check as ollama_health
from backend.modules.voice.pipeline import transcribe_audio_bytes
from backend.modules.voice.tts import synthesize as tts_synthesize, health_check as tts_health


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("plasma")


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
            # Import inside function to avoid startup cost if model is huge
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

    yield
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
# UI
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    """Serve the web UI (push-to-talk page)."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"name": "Plasma", "version": "0.1.0", "status": "online"}


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
    data = await audio.read()
    log.info(f"Received audio blob: {len(data)} bytes, session={session_id}")

    asr_result = await asyncio.to_thread(transcribe_audio_bytes, data)
    transcript = asr_result.get("text", "").strip()

    if not transcript:
        return {
            "session_id": session_id,
            "transcript": "",
            "reply": "(I couldn't hear anything.)",
            "error": asr_result.get("error"),
            "audio_b64": None,
        }

    reply = await asyncio.to_thread(handle_chat, session_id, transcript)

    # Synthesize reply audio with Piper (may fail gracefully — still return text)
    audio_b64 = None
    if plasma_config.TTS_ENABLED:
        try:
            wav_bytes = await asyncio.to_thread(tts_synthesize, reply)
            if wav_bytes:
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
                log.info(f"TTS audio encoded: {len(audio_b64)} b64 chars")
        except Exception as e:
            log.warning(f"TTS synthesis failed: {e}")

    return {
        "session_id": session_id,
        "transcript": transcript,
        "reply": reply,
        "asr_latency_s": asr_result.get("latency"),
        "audio_b64": audio_b64,
    }


# ---------------------------------------------------------------------------
# WebSocket (reserved)
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_voice(ws: WebSocket):
    """Voice WebSocket placeholder (reserved for future streaming use)."""
    await ws.accept()
    log.info("Voice WebSocket connected")
    try:
        await ws.send_json({"type": "hello", "message": "Plasma voice channel ready"})
        while True:
            msg = await ws.receive_text()
            log.info(f"Received: {msg}")
            await ws.send_json({"type": "echo", "text": msg})
    except WebSocketDisconnect:
        log.info("Voice WebSocket disconnected")