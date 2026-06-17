"""Download Arabic Piper TTS voice (ar_JO-kareem-medium).

Usage:
    python scripts/download_ar_voice.py

Downloads to: voices/ar_JO-kareem-medium.onnx (and .onnx.json)
Then add to .env:
    TTS_VOICE_AR=voices/ar_JO-kareem-medium.onnx
"""
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    "/ar/ar_JO/kareem/medium"
)
_FILES = [
    "ar_JO-kareem-medium.onnx",
    "ar_JO-kareem-medium.onnx.json",
]


def _make_opener() -> urllib.request.OpenerDirector:
    """Build a URL opener that trusts the OS/corporate cert store."""
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        ctx = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def download_ar_voice(verbose: bool = True) -> Path:
    """Download the Arabic Piper voice into voices/ and return the .onnx path.

    Reusable by the setup wizard and the command-line entrypoint below.
    Skips files that already exist. Raises on a failed download.
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
        onnx_path = download_ar_voice(verbose=True)
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    print(f"\nVoice saved to: {onnx_path.parent}")
    print("Add this to your .env:")
    print("  TTS_VOICE_AR=voices/ar_JO-kareem-medium.onnx")
    print("\nAlso set for Arabic recognition:")
    print("  WHISPER_MODEL=small")
    print("  WHISPER_LANGUAGE=auto")
    print("  WHISPER_ALLOWED_LANGS=en,de,ar")


if __name__ == "__main__":
    main()
