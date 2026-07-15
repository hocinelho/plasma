"""Tests for laptop-WiFi RSSI motion sensing (backend/modules/sense/rssi_sensor.py)."""
from backend.modules.sense.rssi_sensor import (
    MotionDetector,
    netsh_blocker_hint,
    parse_netsh_signal,
    parse_proc_wireless,
    percent_to_dbm,
)

# ── parsers ────────────────────────────────────────────────────────────────

NETSH_EN = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    State                  : connected
    SSID                   : HomeNet
    Radio type             : 802.11ax
    Signal                 : 86%
    Channel                : 44
"""

NETSH_DE = """
Es ist 1 Schnittstelle auf dem System vorhanden:

    Name                   : WLAN
    Status                 : Verbunden
    SSID                   : HomeNet
    Signal                 : 72%
    Kanal                  : 44
"""

PROC_WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
 wlan0: 0000   54.  -56.  -256        0      0      0      0      0        0
"""


def test_percent_to_dbm_linear_map():
    assert percent_to_dbm(100) == -50.0
    assert percent_to_dbm(0) == -100.0
    assert percent_to_dbm(86) == -57.0


def test_parse_netsh_english_and_german():
    assert parse_netsh_signal(NETSH_EN) == percent_to_dbm(86)
    assert parse_netsh_signal(NETSH_DE) == percent_to_dbm(72)


def test_parse_netsh_no_signal():
    assert parse_netsh_signal("State : disconnected") is None


NETSH_LOCATION_BLOCKED_DE = """
Es ist 1 Schnittstelle auf dem System vorhanden:
Netzwerkshellbefehle benötigen Standortberechtigungen für den Zugriff auf WLAN-Informationen.
Hier ist den URI für die Seite „Standort" in der App „Einstellungen":
‚ms-settings:privacy-location
Die Funktion WlanQueryInterface gibt den Fehler 5 zurück.
"""


def test_netsh_blocker_hint_location_services():
    hint = netsh_blocker_hint(NETSH_LOCATION_BLOCKED_DE)
    assert hint is not None and "Location Services" in hint


def test_netsh_blocker_hint_disconnected():
    hint = netsh_blocker_hint("    Status                  : getrennt")
    assert hint is not None and "not connected" in hint
    assert netsh_blocker_hint(NETSH_EN) is None


def test_parse_proc_wireless_level():
    assert parse_proc_wireless(PROC_WIRELESS) == -56.0


# ── motion detector ────────────────────────────────────────────────────────

def _feed(det, values, t0=0.0, dt=0.33):
    """Feed a list of RSSI values with evenly spaced timestamps; return last t."""
    t = t0
    for v in values:
        det.add_sample(v, t=t)
        t += dt
    return t - dt


def _quiet(n, base=-57.0):
    """A calm signal: tiny alternating ripple, way below any motion threshold."""
    return [base + (0.1 if i % 2 else -0.1) for i in range(n)]


def _busy(n, base=-57.0):
    """A disturbed signal: person walking through the path, ±4 dB swings."""
    return [base + (4.0 if i % 2 else -4.0) for i in range(n)]


def test_quiet_room_never_motion():
    det = MotionDetector(warmup_s=5.0, presence_hold_s=60.0)
    t = _feed(det, _quiet(90))  # ~30s of calm
    st = det.status(t)
    assert st["motion"] is False
    assert st["present"] is False
    assert st["connected"] is True


def test_motion_detected_and_presence_holds():
    det = MotionDetector(warmup_s=5.0, presence_hold_s=60.0)
    t = _feed(det, _quiet(90))                     # learn baseline
    t = _feed(det, _busy(30), t0=t + 0.33)         # ~10s of movement
    st = det.status(t)
    assert st["motion"] is True
    assert st["present"] is True
    # Movement stops; presence must hold within presence_hold_s...
    t2 = _feed(det, _quiet(90), t0=t + 0.33)
    st = det.status(t2)
    assert st["motion"] is False
    assert st["present"] is True
    # ...and decay after it.
    st = det.status(t2 + 61.0)
    assert st["present"] is False


def test_no_motion_during_warmup():
    det = MotionDetector(warmup_s=30.0, presence_hold_s=60.0)
    t = _feed(det, _busy(30))  # ~10s of swings, still inside warmup
    st = det.status(t)
    assert st["warming_up"] is True
    assert st["motion"] is False


def test_disconnected_reports_not_connected():
    det = MotionDetector()
    st = det.add_sample(None, t=0.0)
    assert st["connected"] is False
    assert st["present"] is False
    assert st["rssi_dbm"] is None


def test_status_shape_for_bridge():
    """The bridge forwards these keys; make sure they exist."""
    det = MotionDetector()
    st = det.add_sample(-57.0, t=0.0)
    for key in ("ok", "connected", "warming_up", "motion", "motion_level",
                "present", "rssi_dbm", "sigma_db", "threshold_db",
                "last_motion_ago_s", "samples"):
        assert key in st
