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


def _warn_if_a_newer_copy_is_nested(root: Path) -> None:
    """Shout when this checkout contains another one inside it.

    `git clone` into an existing folder produces plasma\\plasma, leaving two
    complete copies. Both launch, both serve on port 8000, and the outer one is
    usually the stale one — so you edit .env in one, pull updates into one, and
    run the other. The symptoms are maddening: settings that "don't apply",
    fixes that "didn't work", files that are not where you just put them.

    Cheap to detect, and worth a loud line at startup.
    """
    nested = root / root.name / "run_plasma.py"
    if not nested.is_file():
        return
    bar = "!" * 66
    print(f"\n{bar}")
    print("  THERE IS ANOTHER PLASMA INSIDE THIS ONE:")
    print(f"      this one : {root}")
    print(f"      also here: {nested.parent}")
    print("  You are almost certainly meant to run the inner one. Settings and")
    print("  updates applied there will have no effect here.")
    print(f"      cd {nested.parent}")
    print("      python run_plasma.py")
    print(f"{bar}\n")


def main() -> None:
    root = _find_project_root()
    _warn_if_a_newer_copy_is_nested(root)

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
