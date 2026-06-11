#!/usr/bin/env python3
"""
Plasma launcher — starts the FastAPI server and opens the browser.

Used both for development (`python run_plasma.py`) and as the PyInstaller
entry point for the Windows installer (PA-46).
"""
from __future__ import annotations

import os
import sys
import webbrowser
import threading
from pathlib import Path


def _find_project_root() -> Path:
    """Resolve project root whether running from source or frozen bundle."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def main() -> None:
    root = _find_project_root()

    os.environ.setdefault("PLASMA_PROJECT_ROOT", str(root))

    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(root))

    host = os.getenv("PLASMA_HOST", "127.0.0.1")
    port = int(os.getenv("PLASMA_PORT", "8000"))

    def _open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=not getattr(sys, "frozen", False),
    )


if __name__ == "__main__":
    main()
