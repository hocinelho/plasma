"""Raise a hand at the camera and she waves back and says hello.

Runs the real /ws/perception-input handler end to end through FastAPI's
TestClient. Only the pieces that need an actual camera or mediapipe are
mocked — this environment has neither. The reaction wiring itself (the
DebouncedTrigger threshold/cooldown, and proactive_tts.fire being called with
the right text and gesture) runs unmocked.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _frame():
    return np.zeros((10, 10, 3), dtype=np.uint8)


def _hand(raised: bool):
    return {
        "handedness": "Right",
        "finger_count": 5 if raised else 0,
        "fingers": [1, 1, 1, 1, 1],
        "gesture": "open_palm" if raised else "fist",
        "raised": raised,
    }


@pytest.fixture
def app_client():
    app = pytest.importorskip("backend.main", reason="app deps not installed").app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture
def wired(app_client):
    """The websocket route, with camera decode + the perceiver mocked and
    proactive_tts.fire spied on. Yields (app_client, perceiver_mock, fire_mock)."""
    import backend.main as main_mod
    with patch("backend.modules.vision.capture.decode_frame_bytes", return_value=_frame()), \
         patch("backend.modules.vision.perception.get_perceiver") as get_p, \
         patch.object(main_mod.proactive_tts, "fire") as fire:
        perceiver = MagicMock()
        get_p.return_value = perceiver
        yield app_client, perceiver, fire


def _send(ws, n):
    for _ in range(n):
        ws.send_json({"frame": "eA==", "language": "en"})
        ws.receive_json()


class TestWaveReaction:
    def test_a_sustained_raised_hand_triggers_a_wave_and_hello(self, wired):
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": [_hand(True)]}
        with client.websocket_connect("/ws/perception-input") as ws:
            _send(ws, 3)   # _WAVE_FRAMES

        fire.assert_called_once()
        args, kwargs = fire.call_args
        assert args[0] == "Hello!"
        assert kwargs.get("gesture") == "handup"

    def test_a_lowered_hand_never_waves(self, wired):
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": [_hand(False)]}
        with client.websocket_connect("/ws/perception-input") as ws:
            _send(ws, 8)

        fire.assert_not_called()

    def test_no_hands_in_frame_never_waves(self, wired):
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": []}
        with client.websocket_connect("/ws/perception-input") as ws:
            _send(ws, 8)

        fire.assert_not_called()

    def test_one_frame_is_not_enough(self, wired):
        """A single misdetected frame must not fire the reaction."""
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": [_hand(True)]}
        with client.websocket_connect("/ws/perception-input") as ws:
            _send(ws, 2)   # one short of _WAVE_FRAMES

        fire.assert_not_called()

    def test_holding_the_hand_up_does_not_wave_on_every_frame(self, wired):
        """Sends far more than _WAVE_FRAMES in one held gesture — must fire
        exactly once, not once per frame."""
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": [_hand(True)]}
        with client.websocket_connect("/ws/perception-input") as ws:
            _send(ws, 20)

        fire.assert_called_once()

    def test_the_greeting_language_follows_the_request(self, wired):
        client, perceiver, fire = wired
        perceiver.perceive.return_value = {"faces": [], "hands": [_hand(True)]}
        with client.websocket_connect("/ws/perception-input") as ws:
            for _ in range(3):
                ws.send_json({"frame": "eA==", "language": "de"})
                ws.receive_json()

        args, kwargs = fire.call_args
        assert args[0] == "Hallo!"
