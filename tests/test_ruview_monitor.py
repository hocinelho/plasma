"""Tests for the RuView presence monitor's transition → announcement logic."""
from unittest.mock import patch, MagicMock

from backend.modules.sense import ruview_monitor as rm


def test_reading_counts_shapes():
    assert rm._reading_counts({"count": 3}) == (3, {})
    assert rm._reading_counts({"present": True}) == (1, {})
    assert rm._reading_counts({"present": False}) == (0, {})
    total, rooms = rm._reading_counts({"rooms": {"living room": {"count": 1}}})
    assert total == 1 and rooms == {"living room": 1}


def _run_loop_once_per_reading(mon, readings):
    """Drive _loop with a scripted sequence of poll() results; capture announces."""
    said = []
    calls = {"i": 0}

    def fake_poll():
        i = calls["i"]
        calls["i"] += 1
        if i >= len(readings):
            mon._stop_event.set()
            return None
        return readings[i]

    # No cooldown between alerts for the test; no real waiting.
    mon._cooldown_s = 0.0
    mon._poll_s = 0.0
    mon._language = "en"
    with patch.object(mon, "_poll", side_effect=fake_poll), \
         patch.object(mon, "_announce", side_effect=lambda t: said.append(t)), \
         patch.object(mon._stop_event, "wait", return_value=False):
        mon._loop()
    return said


def test_announces_arrival_and_empty():
    mon = rm.RuViewMonitor()
    said = _run_loop_once_per_reading(mon, [{"count": 0}, {"count": 1}, {"count": 0}])
    joined = " ".join(said).lower()
    assert "arrived home" in joined
    assert "empty" in joined


def test_announces_room_entry():
    mon = rm.RuViewMonitor()
    said = _run_loop_once_per_reading(mon, [
        {"count": 1, "rooms": {"living room": 0, "kitchen": 1}},
        {"count": 2, "rooms": {"living room": 1, "kitchen": 1}},
    ])
    assert any("living room" in s.lower() for s in said)


def test_no_alert_when_unchanged():
    mon = rm.RuViewMonitor()
    said = _run_loop_once_per_reading(mon, [{"count": 1}, {"count": 1}, {"count": 1}])
    assert said == []
