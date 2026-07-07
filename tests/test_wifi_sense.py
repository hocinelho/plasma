"""Tests for the RuView WiFi-sensing skill (no network — HTTP mocked)."""
from unittest.mock import patch, MagicMock

from backend.skills import wifi_sense as w


def _resp(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    return r


def test_self_test():
    assert w.self_test() is True


def test_extract_room():
    assert w._extract_room("who is in the living room") == "living room"
    assert w._extract_room("is anyone in the kitchen?") == "kitchen"
    assert w._extract_room("is anyone home") is None


def test_interpret_counts():
    assert "2 people" in w._interpret({"count": 2}, None, False)
    assert "one person" in w._interpret({"count": 1}, None, False)
    assert "no one" in w._interpret({"count": 0}, None, False).lower()
    assert "one person" in w._interpret({"present": True}, None, False)


def test_interpret_room():
    out = w._interpret({"rooms": {"living room": {"count": 1}}}, "living room", False)
    assert "living room" in out and "1" in out


def test_disabled_message():
    with patch.object(w.config, "RUVIEW_ENABLED", False):
        out = w.run({"utterance": "is anyone home"})
    assert "isn't set up" in out.lower() or "ruview" in out.lower()


def test_unreachable_message():
    cfg = MagicMock()
    cfg.RUVIEW_ENABLED = True
    cfg.RUVIEW_URL = "http://localhost:3000"
    cfg.RUVIEW_API_KEY = ""
    with patch.object(w, "config", cfg), \
         patch.object(w, "http_get", side_effect=Exception("refused")):
        out = w.run({"utterance": "is anyone home"})
    assert "can't reach" in out.lower()


def test_query_success():
    cfg = MagicMock()
    cfg.RUVIEW_ENABLED = True
    cfg.RUVIEW_URL = "http://localhost:3000"
    cfg.RUVIEW_API_KEY = ""
    with patch.object(w, "config", cfg), \
         patch.object(w, "http_get", return_value=_resp({"count": 3})):
        out = w.run({"utterance": "how many people are home"})
    assert "3 people" in out


def test_start_alerts_toggle():
    cfg = MagicMock()
    cfg.RUVIEW_ENABLED = True
    cfg.RUVIEW_URL = "http://localhost:3000"
    fake_mon = MagicMock()
    fake_mon.start_watching.return_value = True
    import sys, types
    mod = types.ModuleType("backend.modules.sense.ruview_monitor")
    mod.ruview_monitor = fake_mon
    with patch.object(w, "config", cfg), \
         patch.dict(sys.modules, {"backend.modules.sense.ruview_monitor": mod}):
        out = w.run({"utterance": "watch the house", "language": "en"})
    fake_mon.start_watching.assert_called_once()
    assert "watch the house" in out.lower()


def test_stop_alerts_toggle():
    cfg = MagicMock()
    cfg.RUVIEW_ENABLED = True
    fake_mon = MagicMock()
    import sys, types
    mod = types.ModuleType("backend.modules.sense.ruview_monitor")
    mod.ruview_monitor = fake_mon
    with patch.object(w, "config", cfg), \
         patch.dict(sys.modules, {"backend.modules.sense.ruview_monitor": mod}):
        out = w.run({"utterance": "stop watching the house", "language": "en"})
    fake_mon.stop_watching.assert_called_once()
    assert "stop" in out.lower()
