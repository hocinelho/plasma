"""
Plasma - main backend entrypoint.

For now: health check + WebSocket placeholder.
Future steps will wire in ASR, router, memory, TTS.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pydantic import BaseModel
from backend.core.config import config as plasma_config
from backend.modules.router.chat_service import handle_chat
from backend.modules.router.ollama_client import health_check as ollama_health
from fastapi import UploadFile, File, Form
from backend.modules.voice.pipeline import transcribe_audio_bytes
from fastapi.responses import FileResponse
from pathlib import Path
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("plasma")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Plasma backend starting up...")
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
    allow_origins=["http:@app.get("/")
async def root():
    """Serve the web UI."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return ({"name": "Plasma", "version": "0.1.0", "status": "online"}

@app.get("/health"))
async def health():
    ollama = ollama_health()
    return {
        "status": "ok",
        "config": plasma_config.summary(),
        "components": {
            "backend": "ok",
            "memory": "ok",
            "router": "ok" if ollama.get("reachable") else "ollama_unreachable",
            "asr": "not_initialized",
            "tts": "not_initialized",
        },
        "ollama": ollama,
    }
class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Synchronous chat: user message -> Ollama (with memory) -> reply."""
    import asyncio
    # Ollama call is blocking; run in a threadpool so we don't block the event loop
    reply = await asyncio.to_thread(handle_chat, req.session_id, req.message)
    return ChatResponse(session_id=req.session_id, reply=reply)
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

    # Transcribe off the event loop so we don't block
    asr_result = await asyncio.to_thread(transcribe_audio_bytes, data)
    transcript = asr_result.get("text", "").strip()

    if not transcript:
        return {
            "session_id": session_id,
            "transcript": "",
            "reply": "(I couldn't hear anything.)",
            "error": asr_result.get("error"),
        }

    # Pass to existing chat handler
    reply = await asyncio.to_thread(handle_chat, session_id, transcript)

    return {
        "session_id": session_id,
        "transcript": transcript,
        "reply": reply,
        "asr_latency_s": asr_result.get("latency"),
    }
@app.websocket("/ws")
async def websocket_voice(ws: WebSocket):
    """Voice WebSocket placeholder. Step 5 will wire in ASR streaming."""
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