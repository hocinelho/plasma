"""Basic smoke test for the Plasma backend."""
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_root_serves_the_ui():
    """`/` serves frontend/index.html.

    It used to return a JSON banner, and this test still asserted that long
    after the UI replaced it — invisibly, because the whole file failed to
    import on any machine without faster-whisper, so it was never collected.
    The JSON is now only the fallback for a missing index.html.
    """
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "PLASMA" in r.text


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "components" in data


def test_wake_websocket_accepts_a_browser():
    """The old `/ws` echo endpoint is long gone; `/ws/wake` replaced it.

    It is a one-way broadcast — the server pushes {"type": "wake"} when the
    wake word fires and expects nothing back — so all there is to assert is
    that a browser can connect and the server holds the connection open.
    """
    with client.websocket_connect("/ws/wake") as ws:
        assert ws is not None


def test_the_removed_echo_endpoint_is_really_gone():
    """Guards against the stale expectation coming back."""
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect("/ws"):
            pass