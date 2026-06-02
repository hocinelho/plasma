"""Download German Piper TTS voice (de_DE-thorsten-medium).

Usage:
    python scripts/download_de_voice.py

Downloads to: voices/de_DE-thorsten-medium.onnx (and .onnx.json)
Then add to .env:
    TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx
"""
import sys
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


def main() -> None:
    from backend.core.http_client import get as http_get

    out_dir = Path(__file__).resolve().parents[1] / "voices"
    out_dir.mkdir(exist_ok=True)

    for fname in _FILES:
        url = f"{_BASE}/{fname}"
        dest = out_dir / fname
        if dest.exists():
            print(f"Already exists: {dest}")
            continue
        print(f"Downloading {fname} ...", end=" ", flush=True)
        try:
            resp = http_get(url, timeout=120.0)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            size_mb = len(resp.content) / 1_048_576
            print(f"done ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"FAILED: {e}")
            sys.exit(1)

    print(f"\nVoice saved to: {out_dir}")
    print("Add this to your .env:")
    print(f"  TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx")
    print("\nAlso set for German recognition:")
    print("  WHISPER_MODEL=small")
    print("  WHISPER_LANGUAGE=auto")


if __name__ == "__main__":
    main()
