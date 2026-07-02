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


def _make_console_unicode_safe() -> None:
    """Stop Windows consoles from raising on Unicode log output.

    Some Windows terminals use a legacy code page; uvicorn's coloured records
    then trigger '--- Logging error ---'. Reconfiguring the streams to UTF-8 with
    errors='replace' makes every handler tolerant. No-op on platforms that don't
    need it.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def main() -> None:
    _make_console_unicode_safe()
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
    bar = "-" * 60
    print(f"\n{bar}")
    print("  Plasma is serving over HTTPS. On your phone (SAME Wi-Fi), open:")
    print()
    print(f"      >>> https://{ips[0]}:{port}/camera   <-- try this one first")
    for ip in ips[1:]:
        print(f"          https://{ip}:{port}/camera")
    print()
    print("  1) Phone warns about the certificate -> Advanced -> Proceed.")
    print("  2) If it just spins / times out, Windows Firewall is blocking it.")
    print("     Open PowerShell AS ADMINISTRATOR and run:")
    print(f'       New-NetFirewallRule -DisplayName "Plasma" -Direction Inbound '
          f"-LocalPort {port} -Protocol TCP -Action Allow -Profile Private,Public")
    print("  3) Still nothing? Your Wi-Fi may isolate devices (common on work/")
    print("     campus networks). Use a phone hotspot for both PC and phone.")
    print(f"{bar}\n")

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("PLASMA_HOST", "0.0.0.0"),
        port=port,
        log_level="info",
        reload=False,
        use_colors=False,   # avoid ANSI colour codes that break legacy consoles
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
    )


if __name__ == "__main__":
    main()
