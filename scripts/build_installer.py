#!/usr/bin/env python3
"""
PA-46 — Build a standalone Plasma distribution for Windows.

Usage:
    python scripts/build_installer.py

Produces:  dist/Plasma/Plasma.exe  (one-folder mode)

Requirements:
    pip install pyinstaller

The resulting folder can be zipped and shared.
Users only need Ollama installed separately.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    spec = ROOT / "plasma.spec"
    if not spec.exists():
        print(f"ERROR: {spec} not found", file=sys.stderr)
        sys.exit(1)

    dist = ROOT / "dist"
    build = ROOT / "build"
    if dist.exists():
        shutil.rmtree(dist)
    if build.exists():
        shutil.rmtree(build)

    print("Building Plasma with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(spec),
    ]
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: PyInstaller build failed", file=sys.stderr)
        sys.exit(1)

    output = dist / "Plasma"
    if not output.exists():
        print("ERROR: dist/Plasma not created", file=sys.stderr)
        sys.exit(1)

    env_example = ROOT / ".env.example"
    env_dest = output / ".env"
    if env_example.exists() and not env_dest.exists():
        shutil.copy2(env_example, env_dest)

    plasma_dir = output / ".plasma"
    plasma_dir.mkdir(exist_ok=True)

    print(f"\nBuild complete: {output}")
    print(f"  Run:  {output / 'Plasma.exe'}")
    print("  Make sure Ollama is running: ollama serve")


if __name__ == "__main__":
    main()
