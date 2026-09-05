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

# Read .env the same way the app does, so checks that depend on settings
# (which LLM model is configured, which voice) see what Plasma will see.
# Without this the model check silently skipped: OLLAMA_MODEL was unset in the
# environment even though .env defines it.
try:
    from dotenv import load_dotenv
    if (ROOT / ".env").is_file():
        load_dotenv(ROOT / ".env")
except Exception:
    pass

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

    nested = ROOT / ROOT.name / "run_plasma.py"
    if nested.is_file():
        check(FAIL, "duplicate checkout",
              f"there is another Plasma inside this one, at {nested.parent}. "
              f"Settings and updates you apply in one will not affect the "
              f"other. Use the inner one: cd {nested.parent}")

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
    # Without it identify() returns None for every face, so she never greets
    # anyone by name and never notices a stranger to ask about. Nothing
    # errors — the feature is simply not there, which is precisely the kind
    # of silence this script exists to break.
    "deepface": ("remembering faces by name", "pip install deepface"),
    # Only serve_phone.py needs this, so it is not fatal for a desktop run —
    # but it IS fatal for the phone, and finding that out from a traceback
    # instead of from here is the exact failure this script exists to prevent.
    "cryptography": ("Plasma on your phone (serve_phone.py)",
                     "pip install cryptography"),
}


def check_speech() -> None:
    """Importing faster-whisper is not the same as being able to use it.

    find_spec() only says the package is on disk. Actually importing it loads
    ctranslate2 and PyTorch, which load native DLLs — and a locked-down work
    machine can refuse those (Windows application-control policy, WinError
    4551). That failure is invisible until the first time you speak, so force
    it here where it can be explained.
    """
    if importlib.util.find_spec("faster_whisper") is None:
        return                      # already reported by check_packages
    try:
        import faster_whisper       # noqa: F401
        check(OK, "speech recognition", "faster-whisper loads")
    except Exception as e:
        text = str(e)
        if "4551" in text or "application control" in text.lower() \
                or "anwendungssteuerungsrichtlinie" in text.lower():
            detail = ("blocked by this computer's application control policy "
                      "(an IT restriction, not Plasma). Everything else still "
                      "works — type instead of talking, or ask IT to allow "
                      "the .venv folder")
        else:
            detail = f"installed but will not load: {text[:120]}"
        check(WARN, "speech recognition", detail)


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
    stray = ROOT.parent / ".env"
    if env.exists():
        check(OK, ".env", f"loaded from {env}")
    elif stray.exists():
        # The nested-clone trap: .env ends up beside .venv, one level above the
        # repo. Nothing errors — every setting quietly uses its default, which
        # looks like several unrelated bugs at once.
        check(FAIL, ".env",
              f"in the WRONG FOLDER. Found {stray}, but Plasma reads {env}. "
              f"Move it: move \"{stray}\" \"{env}\"")
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

    # (The wake word is reported by check_wake_word, which names the phrase
    # she actually answers to rather than only the file that is missing.)

    voices_dir = ROOT / "voices"
    if voices_dir.exists() and not voices_dir.is_dir():
        # A stray `move` of several files into a non-existent destination
        # produces one file named "voices" instead of a folder. Everything
        # then reports "no voice" while a large file sits in plain sight.
        size_mb = voices_dir.stat().st_size / 1_048_576
        check(FAIL, "TTS voice",
              f"'{voices_dir}' is a FILE ({size_mb:.0f} MB), not a folder — "
              f"delete it and re-download: del \"{voices_dir}\" then "
              f"python scripts/download_female_voice.py kristin")
        return

    voices = list(voices_dir.glob("*.onnx")) if voices_dir.is_dir() else []
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


def check_wake_word() -> None:
    """Which phrase she is actually listening for.

    "Hey Plasma" is the obvious guess and, until the custom model is trained,
    the wrong one — she answers to whichever pre-trained model is configured.
    Nothing errors when you say the wrong phrase; she simply does not wake,
    which is indistinguishable from a broken microphone.
    """
    if os.getenv("WAKE_WORD_ENABLED", "true").lower() != "true":
        check(WARN, "wake word", "disabled — tap her to talk")
        return

    custom = (os.getenv("WAKE_WORD_MODEL_PATH", "") or "").strip()
    if custom and (ROOT / custom).exists():
        check(OK, "wake word", f"custom model {custom}")
        return

    model = (os.getenv("WAKE_WORD_MODEL", "hey_jarvis") or "").strip()
    phrases = {"hey_jarvis": "Hey Jarvis", "alexa": "Alexa",
               "hey_mycroft": "Hey Mycroft", "hey_rhasspy": "Hey Rhasspy"}
    said = phrases.get(model, model)
    detail = f'say "{said}" — NOT "Hey Plasma"'
    if custom:
        detail += f" (WAKE_WORD_MODEL_PATH={custom} does not exist yet)"
    detail += "; for the real one: python scripts/train_hey_plasma.py"
    check(WARN, "wake word", detail)


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
        return

    # Reachable is not the same as ready. A model named in .env but never
    # pulled fails with a bare 404 at the first question, long after this
    # script has said everything looks fine.
    wanted = os.getenv("OLLAMA_MODEL", "")
    if not wanted:
        return
    try:
        import json as _json
        import urllib.request
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=5) as r:
            installed = [m.get("name", "") for m in _json.load(r).get("models", [])]
    except Exception:
        return                       # cannot tell — stay quiet rather than guess

    bare = wanted.split(":")[0]
    if any(m == wanted or m.split(":")[0] == bare for m in installed):
        check(OK, "LLM model", wanted)
    else:
        check(FAIL, "LLM model",
              f"'{wanted}' is set in .env but not installed — run: "
              f"ollama pull {wanted}   (installed: {', '.join(installed) or 'none'})")


def main() -> int:
    print(f"\nPlasma doctor — {ROOT}\n" + "=" * 62)
    for fn in (check_python, check_packages, check_speech, check_data,
               check_avatar, check_wake_word, check_ollama):
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
