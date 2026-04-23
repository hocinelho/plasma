"""
Plasma - main backend entrypoint.

Endpoints:
- GET  /          — serve the web UI (frontend/index.html)
- GET  /health    — health + component status + Ollama probe
- POST /chat      — text chat: user message -> Ollama (with memory) -> reply
- POST /voice/chat — voice chat: WebM/WAV audio -> Whisper -> /chat -> reply
- WS   /ws        — reserved for future streaming use
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import logging

from pydantic import BaseModel

from backend.core.config import config as plasma_config
from backend.modules.router.chat_service import handle_chat
from backend.modules.router.ollama_client import health_check as ollama_health
from backend.modules.voice.pipeline import transcribe_audio_bytes


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("plasma")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Plasma backend starting up...")

    # Warm the Ollama model — loads weights into RAM so the first user call is fast
    try:
        import asyncio, httpx
        async def _warm():
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    await client.post(
                        f"{plasma_config.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                        json={"model": plasma_config.OLLAMA_MODEL, "prompt": "", "keep_alive": "30m"},
                    )
                log.info(f"Ollama model warmed: {plasma_config.OLLAMA_MODEL}")
            except Exception as e:
                log.warning(f"Ollama warmup skipped: {e}")
        asyncio.create_task(_warm())
    except Exception as e:
        log.warning(f"Warmup scheduling failed: {e}")

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
    return {
        "status": "ok",
        "config": plasma_config.summary(),
        "components": {
            "backend": "ok",
            "memory": "ok",
            "router": "ok" if ollama.get("reachable") else "ollama_unreachable",
            "asr": "ok",
            "tts": "not_initialized",
        },
        "ollama": ollama,
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
    import asyncio
    reply = await asyncio.to_thread(handle_chat, req.session_id, req.message)
    return ChatResponse(session_id=req.session_id, reply=reply)


# ---------------------------------------------------------------------------
# Voice chat (browser push-to-talk)
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
    4. Return both the transcript and the text reply
    """
    import asyncio

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
        }

    reply = await asyncio.to_thread(handle_chat, session_id, transcript)

    return {
        "session_id": session_id,
        "transcript": transcript,
        "reply": reply,
        "asr_latency_s": asr_result.get("latency"),
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