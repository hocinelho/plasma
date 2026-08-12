"""Check a Plasma installation and say what is missing.

    python scripts/doctor.py

Runs without starting the app, so it works before the first launch — which is
exactly when you need it, e.g. after moving to a new machine. Reports what is
wrong AND the command that fixes it.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
_results: list[tuple[str, str, str]] = []


def check(status: str, what: str, detail: str = "") -> None:
    _results.append((status, what, detail))


# ── Python ───────────────────────────────────────────────────────────────
def check_python() -> None:
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 10):
        check(FAIL, f"Python {version}", "Plasma needs 3.11 or newer")
    elif v >= (3, 13):
        check(WARN, f"Python {version}",
              f"some dependencies have no wheels for {v.major}.{v.minor} yet "
              "and must compile from source; 3.11/3.12 is safer")
    else:
        check(OK, f"Python {version}")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        check(OK, "virtual environment", sys.prefix)
    else:
        check(WARN, "virtual environment",
              "not active — run .\\.venv\\Scripts\\Activate.ps1")


# ── Python packages ──────────────────────────────────────────────────────
REQUIRED = {
    "fastapi": "the web server",
    "uvicorn": "the web server",
    "httpx": "talking to Ollama",
    "numpy": "audio processing",
    "faster_whisper": "speech recognition",
    "piper": "text to speech",
    "sounddevice": "microphone capture",
    "dotenv": "reading .env",
}
OPTIONAL = {
    "docx": ("meeting minutes as Word files", "pip install python-docx"),
    "openwakeword": ("the 'hey Plasma' wake word", "pip install openwakeword"),
    "cv2": ("camera vision", "pip install opencv-python"),
    # Only serve_phone.py needs this, so it is not fatal for a desktop run —
    # but it IS fatal for the phone, and finding that out from a traceback
    # instead of from here is the exact failure this script exists to prevent.
    "cryptography": ("Plasma on your phone (serve_phone.py)",
                     "pip install cryptography"),
}


def check_packages() -> None:
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    if missing:
        fix = "pip install -r requirements.txt"
        if missing == ["piper"]:
            # Its own package name differs from the module it provides.
            fix = "pip install piper-tts"
        check(FAIL, "required packages",
              f"missing {', '.join(missing)} — run: {fix}")
    else:
        check(OK, "required packages", f"{len(REQUIRED)} present")

    for mod, (what, fix) in OPTIONAL.items():
        if importlib.util.find_spec(mod) is None:
            check(WARN, f"optional: {what}", f"run: {fix}")
        else:
            check(OK, f"optional: {what}")


# ── Your data ────────────────────────────────────────────────────────────
def check_data() -> None:
    env = ROOT / ".env"
    if env.exists():
        check(OK, ".env", "present")
    else:
        check(FAIL, ".env", "missing — copy .env.example to .env and fill it in")

    memory = ROOT / ".plasma" / "memory.sqlite"
    if memory.exists() and memory.stat().st_size > 0:
        kb = memory.stat().st_size / 1024
        check(OK, "memory", f"{kb:.0f} KB of learned facts")
    else:
        check(WARN, "memory",
              "empty — she starts knowing nothing (copy .plasma/memory.sqlite "
              "from your old machine to keep it)")

    wake = ROOT / ".plasma" / "models" / "hey_plasma.onnx"
    check(OK if wake.exists() else WARN, "wake word model",
          "present" if wake.exists() else
          "missing — 'hey Plasma' won't work (push-to-talk still does)")

    voices = list((ROOT / "voices").glob("*.onnx")) if (ROOT / "voices").is_dir() else []
    if voices:
        check(OK, "TTS voice", ", ".join(v.stem for v in voices))
    else:
        check(FAIL, "TTS voice",
              "none — run: python scripts/download_female_voice.py kristin")


# ── The avatar ───────────────────────────────────────────────────────────
def check_avatar() -> None:
    glb = list((ROOT / "frontend" / "avatars").glob("*.glb"))
    check(OK if glb else FAIL, "3D character",
          ", ".join(g.name for g in glb) if glb else "no .glb in frontend/avatars")

    clips = list((ROOT / "frontend" / "animations").glob("*.fbx"))
    idle = [c for c in clips if c.stem.startswith("idle")]
    if clips:
        check(OK, "animations", f"{len(clips)} clips, {len(idle)} idle")
    else:
        check(WARN, "animations", "none — she can talk but not move")

    vendor = ROOT / "frontend" / "vendor" / "talkinghead" / "talkinghead.mjs"
    check(OK if vendor.exists() else FAIL, "avatar renderer",
          "present" if vendor.exists() else "frontend/vendor is missing")


# ── Services ─────────────────────────────────────────────────────────────
def check_ollama() -> None:
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    host = url.split("//", 1)[-1].split("/", 1)[0]
    hostname, _, port = host.partition(":")
    try:
        with socket.create_connection((hostname, int(port or 11434)), timeout=3):
            check(OK, "Ollama", f"reachable at {url}")
    except Exception:
        check(FAIL, "Ollama",
              f"not reachable at {url} — start the Ollama app, or point "
              "OLLAMA_BASE_URL at the machine running it")


def main() -> int:
    print(f"\nPlasma doctor — {ROOT}\n" + "=" * 62)
    for fn in (check_python, check_packages, check_data, check_avatar, check_ollama):
        try:
            fn()
        except Exception as e:                       # never die mid-report
            check(WARN, fn.__name__, f"check itself failed: {e}")

    width = max((len(w) for _, w, _ in _results), default=0) + 4
    for status, what, detail in _results:
        line = f"  [{status}] {what}"
        # Pad to a common column, but never let a long label swallow the space
        # before its detail.
        print(f"{line.ljust(width + 8)} {detail}".rstrip() if detail else line)

    fails = sum(1 for s, _, _ in _results if s == FAIL)
    warns = sum(1 for s, _, _ in _results if s == WARN)
    print("=" * 62)
    if fails:
        print(f"  {fails} blocking problem(s). Fix those, then run this again.")
    elif warns:
        print(f"  Ready to run, with {warns} thing(s) reduced. "
              "Start it:  python run_plasma.py")
    else:
        print("  Everything checks out.  Start it:  python run_plasma.py")
    print()
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
