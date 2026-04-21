"""
Plasma - main backend entrypoint.

For now: health check + WebSocket placeholder.
Future steps will wire in ASR, router, memory, TTS.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

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
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"name": "Plasma", "version": "0.1.0", "status": "online"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "components": {
            "backend": "ok",
            "memory": "not_initialized",
            "router": "not_initialized",
            "asr": "not_initialized",
            "tts": "not_initialized",
        },
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