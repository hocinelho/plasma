"""Shared HTTPS helper that trusts both certifi's bundle and the OS cert store.

On Windows corporate networks a proxy presents a certificate signed by a
company CA that lives in the Windows store but is absent from certifi's
bundle.  httpx loads certifi after ssl.create_default_context(), which
replaces any OS certs that were injected earlier — so monkey-patching ssl at
import time (e.g. truststore) has no effect.

Building the SSL context here — certifi first, Windows store added on top —
gives every skill one place to get a correctly-trusted httpx call.
"""
from __future__ import annotations
import ssl
import platform

import certifi
import httpx

def _build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    if platform.system() == "Windows":
        # Adds corporate/proxy CA certs from the Windows Trusted Root store
        # without replacing the certifi bundle already loaded above.
        ctx.load_default_certs()
    return ctx

_SSL: ssl.SSLContext = _build_ssl_context()


def get(url: str, *, timeout: float = 6.0, **kwargs) -> httpx.Response:
    """Drop-in for httpx.get that trusts the OS cert store on Windows."""
    return httpx.get(url, timeout=timeout, verify=_SSL, **kwargs)
