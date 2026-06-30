"""Tests for the self-signed TLS helper (phone-camera HTTPS)."""
from backend.core import tls


def test_local_ips_returns_list():
    ips = tls.local_ips()
    assert isinstance(ips, list)
    assert "127.0.0.1" not in ips           # loopback excluded
    assert all("169.254." not in ip for ip in ips)  # link-local excluded


def test_ensure_cert_creates_pair(tmp_path):
    cert, key = tls.ensure_cert(tmp_path)
    assert cert.exists() and key.exists()
    assert cert.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert b"PRIVATE KEY" in key.read_bytes()


def test_ensure_cert_is_idempotent(tmp_path):
    c1, k1 = tls.ensure_cert(tmp_path)
    mtime1 = c1.stat().st_mtime
    c2, k2 = tls.ensure_cert(tmp_path)
    # Same files, not regenerated (mtime unchanged).
    assert (c1, k1) == (c2, k2)
    assert c2.stat().st_mtime == mtime1


def test_ensure_cert_includes_localhost_san(tmp_path):
    from cryptography import x509

    cert_path, _ = tls.ensure_cert(tmp_path)
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    names = [str(g.value) for g in san]
    assert "localhost" in names
    assert "127.0.0.1" in names


def test_ensure_cert_regenerates_on_force(tmp_path):
    c1, _ = tls.ensure_cert(tmp_path)
    first = c1.read_bytes()
    c2, _ = tls.ensure_cert(tmp_path, regenerate=True)
    # A fresh keypair/serial → different certificate bytes.
    assert c2.read_bytes() != first
