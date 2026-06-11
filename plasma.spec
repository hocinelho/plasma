# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Plasma — bundles backend + frontend into one folder."""
import os
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "run_plasma.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "frontend"), "frontend"),
        (str(ROOT / "VERSION"), "."),
        (str(ROOT / ".env.example"), "."),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "backend.core.config",
        "backend.core.google_client",
        "backend.core.ms_graph",
        "backend.modules.router.chat_service",
        "backend.modules.router.ollama_client",
        "backend.modules.memory.store",
        "backend.modules.memory.schema",
        "backend.modules.voice.pipeline",
        "backend.modules.voice.asr",
        "backend.modules.voice.tts",
        "backend.modules.voice.wake_monitor",
        "backend.modules.skills.registry",
        "backend.modules.skills.suggester",
        "backend.modules.user.user_md",
        "backend.modules.user.speaker_id",
        "sounddevice",
        "soundfile",
        "numpy",
        "scipy",
        "scipy.signal",
        "httpx",
        "dotenv",
        "msal",
        "PIL",
        "dateutil",
        "spotipy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "IPython"],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Plasma",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Plasma",
)
