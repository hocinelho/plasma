"""
locate_server.py — lightweight HTTP wrapper around locate-anything-cli.

Deploy this on any machine that has locate-anything.cpp built and the GGUF
model downloaded. Plasma's locate skill will POST images here instead of
running the heavy model locally.

Usage (on the server):
    pip install fastapi uvicorn
    LOCATE_ANYTHING_BIN=/path/to/locate-anything-cli \\
    LOCATE_ANYTHING_MODEL=/path/to/locate-anything-q8_0.gguf \\
    python tools/locate_server.py

    # Or with GPU build:
    LOCATE_ANYTHING_BIN=/path/to/locate-anything-cli \\
    LOCATE_ANYTHING_MODEL=/path/to/locate-anything-q8_0.gguf \\
    LOCATE_ANYTHING_MODE=hybrid \\
    LOCATE_SERVER_HOST=0.0.0.0 \\
    LOCATE_SERVER_PORT=8765 \\
    python tools/locate_server.py

Then on the Plasma machine (.env):
    LOCATE_ANYTHING_SERVER_URL=http://<server-ip>:8765

The server accepts POST /detect with JSON body:
    {"image_b64": "<base64-encoded image>", "prompt": "keys", "mode": "hybrid"}
And returns:
    {"detections": [{"label": "keys", "box": [x, y, w, h]}, ...]}
"""
from __future__ import annotations
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ── config from env ──────────────────────────────────────────────────────────
BIN   = os.environ.get("LOCATE_ANYTHING_BIN", "")
MODEL = os.environ.get("LOCATE_ANYTHING_MODEL", "")
MODE  = os.environ.get("LOCATE_ANYTHING_MODE", "hybrid")
HOST  = os.environ.get("LOCATE_SERVER_HOST", "0.0.0.0")
PORT  = int(os.environ.get("LOCATE_SERVER_PORT", "8765"))
TIMEOUT = float(os.environ.get("LOCATE_ANYTHING_TIMEOUT", "120"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("locate-server")


def _check_config() -> None:
    if not BIN or not Path(BIN).exists():
        print(f"ERROR: LOCATE_ANYTHING_BIN not set or not found: {BIN!r}", file=sys.stderr)
        print("       Set LOCATE_ANYTHING_BIN=/path/to/locate-anything-cli", file=sys.stderr)
        sys.exit(1)
    if not MODEL or not Path(MODEL).exists():
        print(f"ERROR: LOCATE_ANYTHING_MODEL not set or not found: {MODEL!r}", file=sys.stderr)
        print("       Set LOCATE_ANYTHING_MODEL=/path/to/locate-anything-q8_0.gguf", file=sys.stderr)
        sys.exit(1)


def _detect(image_path: str, prompt: str, mode: str) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name
    try:
        cmd = [BIN, "detect", "--model", MODEL, "--input", image_path,
               "--prompt", prompt, "--mode", mode, "--output", out_path]
        log.info("Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        if proc.returncode != 0:
            raise RuntimeError(f"CLI failed: {proc.stderr.strip()[:300]}")
        try:
            raw = Path(out_path).read_text(encoding="utf-8")
        except Exception:
            raw = proc.stdout
        try:
            data = json.loads(raw)
        except Exception:
            data = json.loads(proc.stdout)
        return data.get("detections", []) if isinstance(data, dict) else []
    finally:
        Path(out_path).unlink(missing_ok=True)


# ── FastAPI app ───────────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERROR: fastapi and uvicorn are required.", file=sys.stderr)
    print("       Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

app = FastAPI(title="locate-anything server", version="1.0")


class DetectRequest(BaseModel):
    image_b64: str
    prompt: str
    mode: str = MODE


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": Path(MODEL).name, "mode": MODE}


@app.post("/detect")
def detect(req: DetectRequest) -> JSONResponse:
    # Decode the base64 image and write to a temp file
    try:
        image_bytes = base64.b64decode(req.image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    suffix = ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(image_bytes)
        img_path = tf.name

    try:
        detections = _detect(img_path, req.prompt, req.mode)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Detection timed out")
    except Exception as e:
        log.exception("Detection error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        Path(img_path).unlink(missing_ok=True)

    log.info("prompt=%r → %d detection(s)", req.prompt, len(detections))
    return JSONResponse({"detections": detections})


if __name__ == "__main__":
    _check_config()
    log.info("locate-anything server starting on %s:%d", HOST, PORT)
    log.info("  BIN:   %s", BIN)
    log.info("  MODEL: %s", MODEL)
    log.info("  MODE:  %s", MODE)
    uvicorn.run(app, host=HOST, port=PORT)
