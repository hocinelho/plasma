"""PA-76 — Screenshot by voice: "take a screenshot" / "capture the screen"."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

META = {
    "name": "screenshot",
    "description": "Takes a screenshot and saves it to the Desktop.",
    "triggers": [
        "take a screenshot",
        "take screenshot",
        "screenshot",
        "capture the screen",
        "capture screen",
        "save screenshot",
        "grab the screen",
        "screen capture",
    ],
}

_DESKTOP = Path.home() / "Desktop"


def run(args: dict | None = None) -> str:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshot requires Pillow. Run: pip install Pillow"

    try:
        img = ImageGrab.grab()
        _DESKTOP.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _DESKTOP / f"screenshot_{ts}.png"
        img.save(str(path))
        return f"Screenshot saved to your Desktop as screenshot_{ts}.png."
    except Exception as e:
        return f"Couldn't take a screenshot: {e}"


def self_test() -> bool:
    return True
