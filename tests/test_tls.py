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


# ── LAN address selection ────────────────────────────────────────────────
# These need no crypto backend — they are pure ranking logic.

def test_iphone_hotspot_is_not_mistaken_for_a_virtual_adapter():
    """172.20.10.x is an iPhone personal hotspot — a real, reachable network.

    Most of 172.16-31.x is Hyper-V/WSL/Docker, so a blanket rule against 172.x
    pushed the one address the phone could actually reach to the bottom.
    """
    from backend.core.tls import _ip_rank

    hotspot = _ip_rank("172.20.10.12")
    hyperv = _ip_rank("172.31.240.1")
    wsl = _ip_rank("172.31.16.1")
    assert hotspot < hyperv
    assert hotspot < wsl


def test_home_wifi_still_outranks_virtual_adapters():
    from backend.core.tls import _ip_rank

    assert _ip_rank("192.168.1.5") < _ip_rank("172.31.240.1")
    assert _ip_rank("10.0.0.5") < _ip_rank("172.31.240.1")


def test_routed_address_leads_whatever_its_range(monkeypatch):
    """The OS routing table beats any guess made from the address range."""
    import backend.core.tls as tls

    monkeypatch.setattr(tls, "primary_ip", lambda: "172.20.10.12")
    monkeypatch.setattr(tls.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(
        tls.socket, "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, (ip, 0))
                         for ip in ("172.31.240.1", "172.31.16.1", "192.168.1.5")],
    )
    assert tls.local_ips()[0] == "172.20.10.12"


def test_link_local_and_loopback_are_excluded(monkeypatch):
    import backend.core.tls as tls

    monkeypatch.setattr(tls, "primary_ip", lambda: None)
    monkeypatch.setattr(tls.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(
        tls.socket, "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, (ip, 0))
                         for ip in ("127.0.0.1", "169.254.3.4", "192.168.1.5")],
    )
    assert tls.local_ips() == ["192.168.1.5"]
