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


def download_de_voice(verbose: bool = True) -> Path:
    """Download the German Piper voice into voices/ and return the .onnx path.

    Reusable by the setup wizard (POST /api/setup/download/de_voice) and the
    command-line entrypoint below. Skips files that already exist. Raises on a
    failed download so callers can surface the error.
    """
    out_dir = Path(__file__).resolve().parents[1] / "voices"
    out_dir.mkdir(exist_ok=True)

    opener = _make_opener()

    for fname in _FILES:
        url = f"{_BASE}/{fname}"
        dest = out_dir / fname
        if dest.exists():
            if verbose:
                print(f"Already exists: {dest}")
            continue
        if verbose:
            print(f"Downloading {fname} ...", end=" ", flush=True)
        with opener.open(url, timeout=120) as resp:
            data = resp.read()
        dest.write_bytes(data)
        if verbose:
            size_mb = len(data) / 1_048_576
            print(f"done ({size_mb:.1f} MB)")

    return out_dir / _FILES[0]


def main() -> None:
    try:
        onnx_path = download_de_voice(verbose=True)
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    print(f"\nVoice saved to: {onnx_path.parent}")
    print("Add this to your .env:")
    print("  TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx")
    print("\nAlso set for German recognition:")
    print("  WHISPER_MODEL=small")
    print("  WHISPER_LANGUAGE=auto")


if __name__ == "__main__":
    main()
