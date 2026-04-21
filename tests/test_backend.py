"""Basic smoke test for the Plasma backend."""
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Plasma"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "components" in data


def test_websocket():
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ws.send_text("ping")
        echo = ws.receive_json()
        assert echo["type"] == "echo"
        assert echo["text"] == "ping"