"""Download a female Piper TTS voice.

Plasma's avatar is a woman, so a female voice is usually what you want.

Usage:
    python scripts/download_female_voice.py            # en_US-amy-medium
    python scripts/download_female_voice.py --list     # show the choices
    python scripts/download_female_voice.py jenny      # a different one
    python scripts/download_female_voice.py german     # German female voice

Afterwards, put the printed line in your .env, e.g.
    TTS_VOICE_MODEL=voices/en_US-amy-medium.onnx
and restart Plasma.
"""
from __future__ import annotations

import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# name → (path on HuggingFace, model stem, what it sounds like)
VOICES: dict[str, tuple[str, str, str]] = {
    "amy":    ("en/en_US/amy/medium",          "en_US-amy-medium",
               "American English, warm and clear — the default"),
    "kristin": ("en/en_US/kristin/medium",     "en_US-kristin-medium",
                "American English, brighter and younger"),
    "jenny":  ("en/en_GB/jenny_dioco/medium",  "en_GB-jenny_dioco-medium",
               "British English, soft and natural"),
    "alba":   ("en/en_GB/alba/medium",         "en_GB-alba-medium",
               "Scottish English"),
    "german": ("de/de_DE/eva_k/x_low",         "de_DE-eva_k-x_low",
               "German female (pair with TTS_VOICE_DE)"),
}

DEFAULT = "amy"
VOICES_DIR = Path(__file__).resolve().parents[1] / "voices"


def _make_opener() -> urllib.request.OpenerDirector:
    """Build a URL opener that trusts the OS/corporate cert store."""
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        ctx = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def list_voices() -> str:
    lines = ["Available female voices:"]
    for key, (_, stem, desc) in VOICES.items():
        mark = "  (default)" if key == DEFAULT else ""
        lines.append(f"  {key:9} {desc}{mark}")
        lines.append(f"            → voices/{stem}.onnx")
    return "\n".join(lines)


def download_female_voice(name: str = DEFAULT, verbose: bool = True) -> Path:
    """Download one female voice into voices/ and return the .onnx path."""
    name = (name or DEFAULT).lower().strip()
    if name not in VOICES:
        raise ValueError(f"Unknown voice {name!r}. Choose from: {', '.join(VOICES)}")

    subpath, stem, _desc = VOICES[name]
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    opener = _make_opener()
    onnx_path = VOICES_DIR / f"{stem}.onnx"

    for filename in (f"{stem}.onnx", f"{stem}.onnx.json"):
        target = VOICES_DIR / filename
        if target.exists() and target.stat().st_size > 0:
            if verbose:
                print(f"  already have {filename}")
            continue
        url = f"{_HF}/{subpath}/{filename}"
        if verbose:
            print(f"  downloading {filename} ...")
        with opener.open(url, timeout=120) as resp, open(target, "wb") as fh:
            fh.write(resp.read())
        if verbose:
            print(f"    saved {target} ({target.stat().st_size / 1_000_000:.1f} MB)")

    return onnx_path


def main() -> int:
    args = [a for a in sys.argv[1:] if a]
    if args and args[0] in ("--list", "-l", "list"):
        print(list_voices())
        return 0

    name = args[0] if args else DEFAULT
    try:
        path = download_female_voice(name)
    except ValueError as e:
        print(f"ERROR: {e}\n")
        print(list_voices())
        return 2
    except Exception as e:
        print(f"ERROR: download failed: {e}")
        return 1

    rel = f"voices/{path.name}"
    key = "TTS_VOICE_DE" if name == "german" else "TTS_VOICE_MODEL"
    print("\nDone. Add this line to your .env and restart Plasma:\n")
    print(f"    {key}={rel}\n")
    print("Or switch at runtime by saying: \"switch voice to "
          f"{path.stem.split('-')[1]}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
