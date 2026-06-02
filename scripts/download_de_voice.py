"""Download German Piper TTS voice (de_DE-thorsten-medium).

Usage:
    python scripts/download_de_voice.py

Downloads to: voices/de_DE-thorsten-medium.onnx (and .onnx.json)
Then add to .env:
    TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx
"""
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    "/de/de_DE/thorsten/medium"
)
_FILES = [
    "de_DE-thorsten-medium.onnx",
    "de_DE-thorsten-medium.onnx.json",
]


def _make_opener() -> urllib.request.OpenerDirector:
    """Build a URL opener that trusts the OS/corporate cert store."""
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        ctx = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "voices"
    out_dir.mkdir(exist_ok=True)

    opener = _make_opener()

    for fname in _FILES:
        url = f"{_BASE}/{fname}"
        dest = out_dir / fname
        if dest.exists():
            print(f"Already exists: {dest}")
            continue
        print(f"Downloading {fname} ...", end=" ", flush=True)
        try:
            with opener.open(url, timeout=120) as resp:
                data = resp.read()
            dest.write_bytes(data)
            size_mb = len(data) / 1_048_576
            print(f"done ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"FAILED: {e}")
            sys.exit(1)

    print(f"\nVoice saved to: {out_dir}")
    print("Add this to your .env:")
    print("  TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx")
    print("\nAlso set for German recognition:")
    print("  WHISPER_MODEL=small")
    print("  WHISPER_LANGUAGE=auto")


if __name__ == "__main__":
    main()
