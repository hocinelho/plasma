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
import os
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
from backend.modules.voice.proactive_tts import proactive_tts
from backend.modules.vision.monitor import vision_monitor

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
    await proactive_tts.start()

    yield

    await wake_monitor.stop()
    await proactive_tts.stop()
    try:
        from backend.modules.vision.capture import release_camera
        release_camera()
    except Exception:
        pass
    log.info("Plasma backend shutting down...")


app = FastAPI(
    title="Plasma",
    description="Local-first, self-learning voice assistant",
    version="1.0.0",
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


@app.get("/camera")
async def camera_page():
    """Serve the mobile-friendly phone-camera page (streams to perception WS)."""
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "camera.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"error": "camera.html not found"}, status_code=404)


@app.get("/api/network-info")
async def network_info():
    """LAN IPs + the HTTPS phone URLs, so the UI can tell the user where to point
    their phone for the camera page."""
    from backend.core.tls import local_ips
    ips = local_ips()
    https_port = int(os.getenv("PLASMA_HTTPS_PORT", "8443"))
    return {
        "lan_ips": ips,
        "https_port": https_port,
        "phone_urls": [f"https://{ip}:{https_port}/camera" for ip in ips],
    }


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

    # If the locate skill pinned the object to a box, ship the annotated frame
    # so the user *sees* where it is (spoken reply stays clean text).
    locate_image_b64 = None
    try:
        from backend.skills import locate as _locate_skill
        _img_path = _locate_skill.pop_last_annotated()
        if _img_path:
            with open(_img_path, "rb") as _f:
                locate_image_b64 = base64.b64encode(_f.read()).decode("ascii")
    except Exception as _e:
        log.debug("locate image attach skipped: %s", _e)

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
        "image_b64": locate_image_b64,
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


# ---------------------------------------------------------------------------
# WebSocket — proactive TTS alerts (alarms, reminders)
# ---------------------------------------------------------------------------
@app.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    """
    Browser connects here to receive proactive audio alerts.
    On alarm/reminder fire the server sends:
      {"type": "alert", "text": str, "audio_b64": str | null}
    """
    await ws.accept()
    proactive_tts.add_client(ws)
    log.info("Alert WS client connected")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        proactive_tts.remove_client(ws)
        log.info("Alert WS client disconnected")


# ---------------------------------------------------------------------------
# Vision — object detection via MediaPipe (Apache 2.0)
# POST /vision/snapshot   — single-shot: base64 image → labels
# WS   /ws/vision-input   — stream frames from browser/phone → live detections
# ---------------------------------------------------------------------------

class VisionSnapshotRequest(BaseModel):
    """Base64-encoded JPEG or PNG image from any source (local cam, browser, phone)."""
    image_b64: str
    language: str = "en"


@app.post("/vision/snapshot")
async def vision_snapshot(req: VisionSnapshotRequest):
    """
    Decode a base64 image, run MediaPipe object detection, return labels + scores.

    Browser / phone usage (JavaScript):
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth; canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0);
      const b64 = canvas.toDataURL('image/jpeg').split(',')[1];
      fetch('/vision/snapshot', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({image_b64: b64})})
        .then(r => r.json()).then(d => console.log(d.detections));
    """
    try:
        import base64
        from backend.modules.vision.capture import decode_frame_bytes
        from backend.modules.vision.detector import get_detector

        raw = base64.b64decode(req.image_b64)
        frame = await asyncio.to_thread(decode_frame_bytes, raw)
        detector = get_detector()
        detections = await asyncio.to_thread(detector.detect, frame)
        return {"detections": detections, "count": len(detections)}

    except ImportError as exc:
        return JSONResponse(
            {"error": str(exc), "hint": "pip install mediapipe opencv-python"},
            status_code=503,
        )
    except Exception as exc:
        log.warning("vision_snapshot error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.websocket("/ws/vision-input")
async def websocket_vision_input(ws: WebSocket):
    """
    Stream frames from browser / phone camera for continuous detection.

    Send:  {"frame": "<base64 jpeg>"}
    Recv:  {"type": "detections", "detections": [...], "count": N}
           {"type": "error", "message": "..."}

    JavaScript snippet (camera → WS):
      const ws = new WebSocket('ws://localhost:8000/ws/vision-input');
      const video = ...; // getUserMedia stream
      setInterval(() => {
        const canvas = document.createElement('canvas');
        canvas.getContext('2d').drawImage(video, 0, 0);
        ws.send(JSON.stringify({frame: canvas.toDataURL('image/jpeg').split(',')[1]}));
      }, 500); // 2 FPS
      ws.onmessage = e => console.log(JSON.parse(e.data));
    """
    await ws.accept()
    log.info("Vision-input WS client connected")
    try:
        import base64
        from backend.modules.vision.capture import decode_frame_bytes
        from backend.modules.vision.detector import get_detector

        detector = get_detector()

        while True:
            try:
                data = await ws.receive_json()
                frame_b64 = data.get("frame", "")
                if not frame_b64:
                    continue
                raw = base64.b64decode(frame_b64)
                frame = await asyncio.to_thread(decode_frame_bytes, raw)
                detections = await asyncio.to_thread(detector.detect, frame)
                await ws.send_json({"type": "detections", "detections": detections, "count": len(detections)})
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                await ws.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        log.info("Vision-input WS client disconnected")
    except ImportError as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc), "hint": "pip install mediapipe opencv-python"})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Perception — face expression + hand gestures + face identity (MediaPipe + DeepFace)
# POST /vision/perceive    — single-shot: base64 image → expression/gesture/finger count
# POST /api/face/enroll    — base64 image + name → learn this face
# WS   /ws/perception-input — stream frames from browser/phone → live perception
# ---------------------------------------------------------------------------

class PerceiveRequest(BaseModel):
    """Base64-encoded JPEG/PNG image from any camera (local, browser, phone)."""
    image_b64: str
    language: str = "en"
    identify: bool = False


@app.post("/vision/perceive")
async def vision_perceive(req: PerceiveRequest):
    """Decode an image, return face expression + hand gestures (+ optional identity)."""
    try:
        from backend.modules.vision.capture import decode_frame_bytes
        from backend.modules.vision.perception import get_perceiver, summarize

        raw = base64.b64decode(req.image_b64)
        frame = await asyncio.to_thread(decode_frame_bytes, raw)
        perception = await asyncio.to_thread(get_perceiver().perceive, frame)
        summary = summarize(perception, de=req.language == "de")

        identity = None
        if req.identify and perception.get("faces"):
            from backend.modules.vision import face_id
            name, _dist = await asyncio.to_thread(face_id.identify, frame)
            identity = name

        return {"perception": perception, "summary": summary, "identity": identity}

    except ImportError as exc:
        return JSONResponse(
            {"error": str(exc), "hint": "pip install mediapipe opencv-python"},
            status_code=503,
        )
    except Exception as exc:
        log.warning("vision_perceive error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=400)


class FaceEnrollRequest(BaseModel):
    image_b64: str
    name: str


@app.post("/api/face/enroll")
async def face_enroll(req: FaceEnrollRequest):
    """Learn a face from a single base64 image so Plasma can recognize it later."""
    try:
        from backend.modules.vision.capture import decode_frame_bytes
        from backend.modules.vision import face_id

        raw = base64.b64decode(req.image_b64)
        frame = await asyncio.to_thread(decode_frame_bytes, raw)
        msg = await asyncio.to_thread(face_id.enroll, req.name.strip(), frame)
        return {"ok": True, "message": msg, "people": face_id.list_people()}
    except Exception as exc:
        log.warning("face_enroll error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.get("/api/perception/status")
async def perception_status():
    """Report whether perception deps are available + enrolled faces."""
    from backend.modules.vision import face_id
    mp_ok = True
    try:
        import mediapipe  # noqa: F401
    except Exception:
        mp_ok = False
    from backend.modules.vision import tracker
    return {
        "mediapipe": mp_ok,
        "face_id": face_id.is_available(),
        "people": face_id.list_people(),
        "object_tracking": tracker.is_available(),
        "track_fps": plasma_config.TRACK_FPS,
        "default_fps": plasma_config.PERCEPTION_FPS,
        "enabled_at_boot": plasma_config.PERCEPTION_ENABLED,
    }


@app.websocket("/ws/perception-input")
async def websocket_perception_input(ws: WebSocket):
    """
    Stream frames from a device camera for always-on face/hand tracking.

    Send:  {"frame": "<base64 jpeg>", "language": "en", "identify": true}
    Recv:  {"type": "perception", "perception": {...}, "summary": "...", "identity": "Hocine"|null}
           {"type": "error", "message": "..."}

    Identity (DeepFace) is throttled to FACE_ID_INTERVAL_S so it never eats CPU;
    landmark tracking runs every frame. The browser button starts/stops this
    stream, so there is zero cost when you're not watching.

    Proactive reactions fire via ProactiveTTS (→ /ws/alerts) when:
      • A known person is recognised for the first time (or after GREETING_COOLDOWN_S).
      • The user looks sleepy for SLEEPY_FRAMES_THRESHOLD consecutive frames.
    """
    await ws.accept()
    log.info("Perception-input WS client connected")
    last_identity_t = 0.0
    cached_identity = None

    # ── proactive reaction state ──────────────────────────────────────────
    _GREETING_COOLDOWN_S = 300.0   # re-greet same person at most every 5 min
    _SLEEPY_COOLDOWN_S   = 120.0   # sleepy alert at most every 2 min
    _SLEEPY_THRESHOLD    = 10      # consecutive frames (~1.7 s at 6 fps)
    last_greeted: str | None = None
    last_greeting_t      = 0.0
    last_sleepy_alert_t  = 0.0
    sleepy_frames        = 0

    # DeepFace (TF) takes ~30-60 s to load on the first call.
    # Running identify() as a fire-and-forget task keeps frames flowing
    # while TF initialises; we collect the result on the next iteration.
    _identify_task: asyncio.Task | None = None

    # ── object tracking state ─────────────────────────────────────────────
    last_track_t = 0.0
    cached_objects: list = []          # last reported tracks (boxes + ids)
    track_interval = 1.0 / max(0.5, plasma_config.TRACK_FPS)

    try:
        from backend.modules.vision.capture import decode_frame_bytes
        from backend.modules.vision.perception import get_perceiver, summarize
        from backend.modules.vision import face_id

        perceiver = get_perceiver()
        interval = plasma_config.FACE_ID_INTERVAL_S

        while True:
            try:
                data = await ws.receive_json()
                frame_b64 = data.get("frame", "")
                if not frame_b64:
                    continue
                de = data.get("language", "en") == "de"
                raw = base64.b64decode(frame_b64)
                frame = await asyncio.to_thread(decode_frame_bytes, raw)
                perception = await asyncio.to_thread(perceiver.perceive, frame)

                # Identity: non-blocking background task so TF load never
                # stalls the frame loop.  Collect the result when it's done,
                # start a new task once the throttle interval has elapsed.
                if data.get("identify") and perception.get("faces"):
                    now = time.monotonic()
                    if _identify_task is not None and _identify_task.done():
                        try:
                            name, _ = _identify_task.result()
                            cached_identity = name
                        except Exception as _e:
                            log.debug("face_id task error: %s", _e)
                        _identify_task = None
                    if _identify_task is None and (now - last_identity_t) >= interval:
                        last_identity_t = now
                        _identify_task = asyncio.create_task(
                            asyncio.to_thread(face_id.identify, frame)
                        )

                # ── proactive: greet by name when first seen ──────────────
                now = time.monotonic()
                if cached_identity:
                    new_person = cached_identity != last_greeted
                    cooldown_expired = (now - last_greeting_t) >= _GREETING_COOLDOWN_S
                    if (new_person or cooldown_expired) and (now - last_greeting_t) >= 10.0:
                        lang = "de" if de else "en"
                        greeting = (
                            f"Hallo, {cached_identity}!"
                            if de
                            else f"Hello, {cached_identity}!"
                        )
                        proactive_tts.fire(greeting, lang)
                        last_greeted = cached_identity
                        last_greeting_t = now

                # ── proactive: sleepy alert after sustained drowsiness ─────
                faces = perception.get("faces", [])
                if faces and faces[0].get("expression") == "sleepy":
                    sleepy_frames += 1
                    if sleepy_frames >= _SLEEPY_THRESHOLD:
                        if (now - last_sleepy_alert_t) >= _SLEEPY_COOLDOWN_S:
                            lang = "de" if de else "en"
                            msg = (
                                "Du siehst müde aus. Vielleicht eine kurze Pause?"
                                if de
                                else "You look tired. Maybe take a short break?"
                            )
                            proactive_tts.fire(msg, lang)
                            last_sleepy_alert_t = now
                            sleepy_frames = 0
                else:
                    sleepy_frames = 0

                # ── object detection + tracking (opt-in via track:true) ────
                # Throttled to TRACK_FPS so it never competes with face/hand
                # work; the tracker keeps stable IDs between detection cycles.
                if data.get("track") and plasma_config.TRACK_ENABLED:
                    now = time.monotonic()
                    if now - last_track_t >= track_interval:
                        last_track_t = now
                        try:
                            from backend.modules.vision.detector import get_tracking_detector
                            from backend.modules.vision.tracker import get_tracker
                            # Dedicated lower-threshold detector → richer multi-object;
                            # it already applies TRACK_CONF, so no post-filter needed.
                            dets = await asyncio.to_thread(get_tracking_detector().detect, frame)
                            cached_objects = get_tracker().update(dets)
                        except Exception as _te:
                            log.debug("tracking step error: %s", _te)

                try:
                    fh, fw = int(frame.shape[0]), int(frame.shape[1])
                except Exception:
                    fw = fh = 0

                await ws.send_json({
                    "type": "perception",
                    "perception": perception,
                    "summary": summarize(perception, de),
                    "identity": cached_identity,
                    "objects": cached_objects,
                    "frame_w": fw,
                    "frame_h": fh,
                })
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                await ws.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        if _identify_task and not _identify_task.done():
            _identify_task.cancel()
        log.info("Perception-input WS client disconnected")
    except ImportError as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc), "hint": "pip install mediapipe deepface opencv-python"})
        except Exception:
            pass