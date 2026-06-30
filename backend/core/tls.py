"""
Self-signed TLS for the phone camera.

Phones refuse `getUserMedia` on a plain `http://` LAN origin — the page must be a
secure context (HTTPS or localhost). To make the phone work with zero external
setup, we generate a self-signed certificate that includes the machine's LAN IPs
in its Subject Alternative Names, and serve Plasma over HTTPS with it.

The phone shows a one-time "not private" warning (expected for self-signed) —
tap *Advanced → Proceed* once and the camera works. No internet, no accounts,
no third-party tunnel required.

Pure helpers, no FastAPI imports — easy to unit-test.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import logging
import socket
from pathlib import Path

log = logging.getLogger("plasma.tls")


def local_ips() -> list[str]:
    """Best-effort list of this machine's LAN IPv4 addresses (no loopback)."""
    ips: set[str] = set()
    # Primary route IP — the address a phone on the same network would use.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # Everything the hostname resolves to (covers multi-NIC machines).
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    ips.discard("127.0.0.1")
    return sorted(ip for ip in ips if not ip.startswith("169.254."))


def _san_signature(ips: list[str]) -> str:
    return ",".join(sorted(ips))


def ensure_cert(cert_dir: Path, regenerate: bool = False) -> tuple[Path, Path]:
    """Return (cert_path, key_path), generating a self-signed pair if needed.

    Regenerates when missing, expired, or the LAN IPs changed (e.g. new network),
    so the cert's SANs always match how the phone reaches this machine.
    """
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "plasma.crt"
    key_path = cert_dir / "plasma.key"
    sig_path = cert_dir / "plasma.san"

    ips = local_ips()
    sig = _san_signature(ips)

    fresh = cert_path.exists() and key_path.exists()
    if fresh and sig_path.exists():
        try:
            fresh = sig_path.read_text(encoding="utf-8").strip() == sig
        except Exception:
            fresh = False
    else:
        fresh = False

    if fresh and not regenerate:
        return cert_path, key_path

    _generate(cert_path, key_path, ips)
    sig_path.write_text(sig, encoding="utf-8")
    log.info("Generated self-signed cert for %s → %s", ips or ["localhost"], cert_path)
    return cert_path, key_path


def _generate(cert_path: Path, key_path: Path, ips: list[str]) -> None:
    """Write a self-signed cert + key covering localhost + the given IPs."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    alt_names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in ips:
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Plasma Local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Plasma"),
    ])
    # Fixed reference date (no Date.now-style nondeterminism needed here; this is
    # a long-lived local dev cert). Use UTC explicitly.
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:  # tighten key permissions where the OS supports it
        key_path.chmod(0o600)
    except Exception:
        pass
