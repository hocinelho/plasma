"""When tracking fails, say why — and either reconnect or stop claiming to.

The page showed "reconnecting…" indefinitely while tracking was dead. Two
separate faults produced that:

  * the server sent a perfectly good explanation ("mediapipe isn't
    installed") and then closed, and the close handler immediately painted
    "reconnecting…" over it — the reason survived for about one frame;
  * nothing ever reconnected. The word was decoration.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
MAIN = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")


class TestTheErrorSurvives:
    def test_the_error_is_remembered(self):
        assert "visionLastError = msg.hint" in INDEX

    def test_close_shows_the_error_instead_of_reconnecting(self):
        close = INDEX.split("visionWS.onclose", 1)[1][:1400]
        assert "if (visionLastError)" in close
        # And it must give up rather than retry into the same failure once a
        # second, which would hide the message again.
        assert "visionOn = false;" in close

    def test_the_button_returns_to_its_off_state(self):
        """Otherwise it says "Stop watching" while nothing is watching."""
        close = INDEX.split("visionWS.onclose", 1)[1][:1400]
        assert "👁 Watch me" in close


class TestItActuallyReconnects:
    def test_a_dropped_socket_is_retried(self):
        close = INDEX.split("visionWS.onclose", 1)[1][:1400]
        assert "connectVisionSocket()" in close

    def test_retries_are_bounded_and_backed_off(self):
        assert "VISION_MAX_RETRIES" in INDEX
        close = INDEX.split("visionWS.onclose", 1)[1][:1400]
        assert "Math.pow(2, visionRetries)" in close

    def test_a_good_connection_resets_the_budget(self):
        opened = INDEX.split("visionWS.onopen", 1)[1][:400]
        assert "visionRetries = 0;" in opened

    def test_the_frame_timer_stops_when_the_socket_does(self):
        """It kept firing into a closed socket every 166 ms."""
        close = INDEX.split("visionWS.onclose", 1)[1][:400]
        assert "clearInterval(visionTimer)" in close

    def test_connect_is_separate_from_start(self):
        """Retrying must not re-request the camera each time."""
        assert "function connectVisionSocket()" in INDEX
        start = INDEX.split("async function startVision()", 1)[1].split("function connectVisionSocket", 1)[0]
        assert "getUserMedia" in start
        assert "new WebSocket" not in start


class TestTheServerExplainsItself:
    def test_a_missing_package_is_named_and_logged(self):
        block = MAIN.split("except ImportError as exc:", 1)[1][:700]
        assert "log.warning" in block
        assert "pip install mediapipe" in block

    def test_any_other_failure_is_reported_not_silent(self):
        """Previously only ImportError was handled; everything else closed the
        socket with nothing said, which is what "reconnecting… forever" was."""
        after = MAIN.split("Perception-input WS client disconnected", 1)[1][:1400]
        assert "except Exception as exc:" in after
        assert "log.exception" in after
        assert '"type": "error"' in after
