"""Shared HTTPS helper that trusts the OS certificate store.

On Windows corporate networks a proxy presents a certificate signed by a
company CA.  certifi's bundle doesn't include it, and Python's
ssl.load_default_certs() misses it too because it doesn't do the on-demand
CA fetching that Windows performs natively — so verification fails with
CERTIFICATE_VERIFY_FAILED on hosts like Wikipedia.

`truststore` fixes this properly: its SSLContext delegates verification to
the OS (Windows CryptoAPI / macOS Security framework), which trusts the
corporate CA.  We build that context once and pass it to every skill's
outbound call.

Escape hatch: set PLASMA_INSECURE_SSL=true in .env to skip verification
entirely (only for trusted local/dev networks).
"""
from __future__ import annotations
import os
import ssl
import logging

import certifi
import httpx

log = logging.getLogger("plasma.http")

_INSECURE = os.getenv("PLASMA_INSECURE_SSL", "false").lower() == "true"


def _build_verify():
    if _INSECURE:
        log.warning("PLASMA_INSECURE_SSL=true — TLS verification DISABLED")
        return False
    # Preferred: OS trust store (handles corporate MITM proxies).
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        log.warning(
            "truststore unavailable — falling back to certifi. If you see "
            "CERTIFICATE_VERIFY_FAILED, run: pip install truststore"
        )
        return ssl.create_default_context(cafile=certifi.where())


_VERIFY = _build_verify()


def get(url: str, *, timeout: float = 6.0, **kwargs) -> httpx.Response:
    """Drop-in for httpx.get that trusts the OS cert store on Windows."""
    return httpx.get(url, timeout=timeout, verify=_VERIFY, **kwargs)


def post(url: str, *, timeout: float = 6.0, **kwargs) -> httpx.Response:
    """Drop-in for httpx.post that trusts the OS cert store on Windows."""
    return httpx.post(url, timeout=timeout, verify=_VERIFY, **kwargs)
