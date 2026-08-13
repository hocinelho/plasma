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


def _firewall_rule_missing(port: int) -> bool:
    """True if Windows Firewall appears to have no inbound rule for `port`.

    Best-effort and non-fatal: a wrong answer here only changes the wording of
    a hint. Querying rules does not need administrator rights.
    """
    if os.name != "nt":
        return False
    try:
        import subprocess
        query = (
            "$p=%d; "
            "$r=Get-NetFirewallPortFilter -ErrorAction SilentlyContinue | "
            "Where-Object { $_.LocalPort -eq $p }; "
            "if ($r) { foreach ($f in $r) { $rule = $f | Get-NetFirewallRule "
            "-ErrorAction SilentlyContinue; if ($rule.Enabled -eq 'True' -and "
            "$rule.Direction -eq 'Inbound' -and $rule.Action -eq 'Allow') "
            "{ Write-Output 'FOUND'; break } } }"
        ) % port
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True, text=True, timeout=12,
        )
        return "FOUND" not in (out.stdout or "")
    except Exception:
        return False          # can't tell — don't cry wolf


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
    try:
        cert_path, key_path = ensure_cert(cert_dir, regenerate=regen)
    except ModuleNotFoundError as exc:
        if exc.name != "cryptography":
            raise
        # Without a certificate there is no HTTPS, and without HTTPS a phone
        # will not grant microphone access — so this is fatal, but it is a
        # one-line fix and deserves to read like one rather than a traceback.
        print(
            "\n  Cannot make the HTTPS certificate: the 'cryptography' package\n"
            "  is not installed in this environment.\n\n"
            "      pip install -r requirements.txt\n\n"
            "  (or just: pip install cryptography)\n\n"
            "  Plasma still runs on this computer without it — python run_plasma.py.\n"
            "  Only the phone needs HTTPS.\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    ips = local_ips() or ["<this-computer-ip>"]
    blocked = _firewall_rule_missing(port)
    bar = "-" * 60
    print(f"\n{bar}")
    print("  Plasma is serving over HTTPS. On your phone, open:")
    print()
    print(f"      >>> https://{ips[0]}:{port}/          <-- the avatar")
    print(f"          https://{ips[0]}:{port}/?stage=1  <-- summon: full screen, listening")
    print(f"          https://{ips[0]}:{port}/wallpaper <-- save her as your wallpaper")
    print(f"          https://{ips[0]}:{port}/camera    <-- phone as a camera")
    if len(ips) > 1:
        print()
        print("  If that address doesn't answer, try:")
        for ip in ips[1:]:
            print(f"          https://{ip}:{port}/")
    print()

    if blocked:
        # By far the most common cause of "it just spins": the request never
        # reaches Python at all, so nothing appears in this log.
        print("  !! WINDOWS FIREWALL HAS NO RULE FOR PORT %d." % port)
        print("     The phone's request will be dropped before it gets here,")
        print("     and you will see a white page that never loads.")
        print("     Open PowerShell AS ADMINISTRATOR and run:")
        print()
        print(f'       New-NetFirewallRule -DisplayName "Plasma" -Direction Inbound '
              f"-LocalPort {port} -Protocol TCP -Action Allow -Profile Private,Public")
        print()
    else:
        print("  1) Phone warns about the certificate -> Advanced -> Proceed.")
        print("  2) If it spins forever, check Windows Firewall allows port %d." % port)

    print("  3) Nothing in this log when you load the page = the request never")
    print("     arrived (firewall, wrong IP, or the network isolates devices).")
    print("  4) On a phone hotspot the PC's address changes each time you")
    print("     reconnect — re-read the address above rather than reusing an old one.")
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
