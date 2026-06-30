#!/usr/bin/env python3
"""
Plasma over HTTPS — so your phone's camera works.

Phones block camera access on plain http:// LAN addresses. This launcher
generates a self-signed certificate (with your computer's LAN IP baked in) and
serves Plasma over https://, which phones accept as a secure context.

Usage:
    python serve_phone.py            # serve on https://0.0.0.0:8443
    PLASMA_HTTPS_PORT=9000 python serve_phone.py

Then, on your phone (same Wi-Fi), open the printed URL, e.g.
    https://192.168.1.42:8443/camera
Tap "Advanced → Proceed" once to accept the self-signed certificate.
No internet, accounts, or tunnels needed — everything stays on your network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def main() -> None:
    root = _find_project_root()
    os.environ.setdefault("PLASMA_PROJECT_ROOT", str(root))
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(root))

    from backend.core.tls import ensure_cert, local_ips

    port = int(os.getenv("PLASMA_HTTPS_PORT", "8443"))
    cert_dir = root / ".plasma" / "certs"
    regen = "--force-cert" in sys.argv
    cert_path, key_path = ensure_cert(cert_dir, regenerate=regen)

    ips = local_ips() or ["<this-computer-ip>"]
    bar = "─" * 56
    print(f"\n{bar}")
    print("  Plasma is serving over HTTPS — open this on your phone:")
    for ip in ips:
        print(f"      https://{ip}:{port}/camera")
    print()
    print("  First time: your phone will warn about the certificate.")
    print("  Tap 'Advanced' → 'Proceed' (it's your own computer).")
    print(f"{bar}\n")

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("PLASMA_HOST", "0.0.0.0"),
        port=port,
        log_level="info",
        reload=False,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
    )


if __name__ == "__main__":
    main()
