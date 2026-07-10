#!/usr/bin/env python3
"""
RuView bridge for Plasma — serves the HTTP endpoints Plasma's WiFi features expect.

The `ruview` pip package is just a DSP library (needs ESP32 CSI hardware and has
no server). This tiny bridge fills the gap:

  * DEMO mode (default) — no hardware, no Docker: streams a simulated walking
    skeleton so you can see Plasma's "🫥 See-through" view and presence alerts
    work immediately.
  * RSSI mode (--rssi) — REAL motion sensing with zero extra hardware: reads
    the laptop's own WiFi signal strength and detects people moving between
    the laptop and the router from the jitter. House-level presence only
    (no rooms, no skeletons, no vitals); the laptop must be ON WiFi.
  * REAL mode — once you have an ESP32-S3 running CSI, plug your `ruview`
    extractor output into `real_scene()` below and run with --real.

Run:
    python scripts/ruview_bridge.py            # demo on http://localhost:3000
    python scripts/ruview_bridge.py --rssi     # real laptop-WiFi motion sensing
    python scripts/ruview_bridge.py --port 3001

Then in Plasma's .env:
    RUVIEW_ENABLED=true
    RUVIEW_URL=http://localhost:3000
    RUVIEW_ALERTS=true      # optional: spoken presence alerts

No external dependencies — pure Python standard library.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# COCO-17 skeleton, as (x, y) offsets from the body centre, roughly 0..1 tall.
_TEMPLATE = [
    (0.00, 0.00),  # 0 nose
    (-0.03, -0.02), (0.03, -0.02),  # 1,2 eyes
    (-0.06, 0.00), (0.06, 0.00),    # 3,4 ears
    (-0.10, 0.15), (0.10, 0.15),    # 5,6 shoulders
    (-0.16, 0.32), (0.16, 0.32),    # 7,8 elbows
    (-0.20, 0.48), (0.20, 0.48),    # 9,10 wrists
    (-0.07, 0.50), (0.07, 0.50),    # 11,12 hips
    (-0.08, 0.72), (0.08, 0.72),    # 13,14 knees
    (-0.09, 0.95), (0.09, 0.95),    # 15,16 ankles
]
_ROOMS = ["living room", "kitchen", "hallway", "bedroom"]

DEMO = True
N_PEOPLE = 3
_START = time.time()


# Floor positions (x,y in 0..1) a demo person walks through — matches the
# default floor plan's rooms so they show up in the right room.
_PATH = [
    (0.50, 0.88),  # entrance
    (0.50, 0.65),  # hallway
    (0.27, 0.27),  # living room
    (0.50, 0.65),  # hallway
    (0.77, 0.20),  # kitchen
    (0.50, 0.65),  # hallway
]


def _walk(t: float, period: float = 32.0) -> tuple[float, float]:
    """Position along the looping path at time t."""
    n = len(_PATH)
    u = (t % period) / period * n
    i = int(u) % n
    f = u - int(u)
    ax, ay = _PATH[i]
    bx, by = _PATH[(i + 1) % n]
    return ax + (bx - ax) * f, ay + (by - ay) * f


def _skeleton(cx: float, swing: float) -> list:
    kp = []
    for i, (ox, oy) in enumerate(_TEMPLATE):
        x = cx + ox
        y = 0.25 + oy * 0.7
        if i in (7, 9):
            x += swing
        if i in (8, 10):
            x -= swing
        kp.append([round(x, 4), round(y, 4)])
    return kp


# Second-floor path (level 1) for the upstairs person.
_PATH_UP = [(0.27, 0.30), (0.50, 0.80), (0.77, 0.30), (0.50, 0.80)]


def _walk_path(path, t, period):
    n = len(path)
    u = (t % period) / period * n
    i = int(u) % n
    f = u - int(u)
    ax, ay = path[i]
    bx, by = path[(i + 1) % n]
    return ax + (bx - ax) * f, ay + (by - ay) * f


def _vitals(t: float, k: int, moving: bool) -> dict:
    """Simulated vitals, shaped like ruview's Breathing/HeartRate extractors.

    Breathing drifts slowly around 14 BPM (resting) or 18 (walking); heart
    around 68 / 88. Real CSI extracts these from the 0.08–0.6 Hz band.
    """
    base_br = 18.0 if moving else 14.0
    base_hr = 88 if moving else 68
    return {
        "breathing_bpm": round(base_br + 1.5 * math.sin(t * 0.05 + k), 1),
        "heart_bpm": int(base_hr + 5 * math.sin(t * 0.03 + k * 2)),
        "vitals_confidence": round(0.85 + 0.1 * math.sin(t * 0.1 + k), 2),
    }


def _demo_people(n_people: int = 3) -> list[dict]:
    """`n_people` simulated occupants spread across floors, some walking."""
    t = time.time() - _START
    people: list[dict] = []
    # Ground floor: one walking the main path, one still in the kitchen.
    px, py = _walk_path(_PATH, t, 32.0)
    people.append({"keypoints": _skeleton(px, 0.06 * math.sin(t * 3.0)),
                   "x": round(px, 4), "y": round(py, 4), "level": 0,
                   **_vitals(t, 1, moving=True)})
    if n_people >= 2:
        people.append({"keypoints": _skeleton(0.77, 0.0), "x": 0.77, "y": 0.20, "level": 0,
                       **_vitals(t, 2, moving=False)})
    # Upstairs: person(s) pacing on level 1 — proves the floor switch works.
    for k in range(3, n_people + 1):
        ux, uy = _walk_path(_PATH_UP, t + k * 7.0, 24.0)
        people.append({"keypoints": _skeleton(ux, 0.05 * math.sin(t * 2.5 + k)),
                       "x": round(ux, 4), "y": round(uy, 4), "level": 1,
                       **_vitals(t, k, moving=True)})
    return people


def real_scene() -> dict:
    """REAL mode hook. Fill this from your ruview + ESP32 CSI pipeline.

    Return the same shape as demo: {"people": [{"keypoints": [[x,y]..], "room": str}],
    "count": int, "present": bool, "rooms": {room: count}}.
    """
    # Example skeleton (replace with live ruview output):
    #   from ruview import PoseEstimator
    #   people = PoseEstimator.esp32_default().extract(csi_source)
    return {"people": [], "count": 0, "present": False, "rooms": {}}


class RssiLoop(threading.Thread):
    """Background sampler: laptop RSSI → MotionDetector, ~3 samples/second."""

    def __init__(self, detector, hz: float = 3.0):
        super().__init__(daemon=True, name="rssi-sensor")
        self.detector = detector
        self.hz = hz
        self.status: dict = {"ok": True, "connected": False, "present": False,
                             "motion": False, "warming_up": True}

    def run(self):
        from backend.modules.sense.rssi_sensor import read_rssi_dbm
        while True:
            self.status = self.detector.add_sample(read_rssi_dbm())
            time.sleep(1.0 / self.hz)


RSSI_LOOP: "RssiLoop | None" = None


def rssi_scene() -> dict:
    """Scene built from the laptop's real RSSI motion detector.

    Honest shape: count is 0 or 1, no rooms, no people/pose — Plasma's
    wifi_sense skill and the RuView alert monitor read count/present as-is.
    """
    st = RSSI_LOOP.status if RSSI_LOOP else {}
    present = bool(st.get("present"))
    return {
        "present": present,
        "count": 1 if present else 0,
        "rooms": {},
        "people": [],
        "has_pose": False,
        "mode": "rssi",
        "connected": st.get("connected"),
        "warming_up": st.get("warming_up"),
        "motion": st.get("motion"),
        "motion_level": st.get("motion_level"),
        "rssi_dbm": st.get("rssi_dbm"),
        "sigma_db": st.get("sigma_db"),
        "threshold_db": st.get("threshold_db"),
        "last_motion_ago_s": st.get("last_motion_ago_s"),
    }


def scene() -> dict:
    if RSSI_LOOP is not None:
        return rssi_scene()
    people = _demo_people(N_PEOPLE) if DEMO else real_scene().get("people", [])
    rooms: dict[str, int] = {}
    for p in people:
        r = p.get("room")
        if r:
            rooms[r] = rooms.get(r, 0) + 1
    return {
        "present": len(people) > 0,
        "count": len(people),
        "rooms": rooms,
        "people": people,
        "has_pose": any("keypoints" in p for p in people),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        data = scene()
        if self.path.rstrip("/") in ("/api/pose", "/pose", "/api/keypoints", "/keypoints"):
            self._send(data)
        elif self.path.rstrip("/") in ("/api/presence", "/presence", "/api/status", "/status", "/api/sensors"):
            # Everything except the (possibly large) pose list.
            self._send({k: v for k, v in data.items() if k not in ("people", "has_pose")})
        elif self.path.rstrip("/") in ("", "/"):
            mode = "rssi" if RSSI_LOOP else ("demo" if DEMO else "real")
            self._send({"service": "ruview-bridge", "mode": mode, "endpoints": ["/api/pose", "/api/presence"]})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):  # quiet
        pass


def main():
    global DEMO, RSSI_LOOP
    ap = argparse.ArgumentParser(description="RuView → Plasma bridge server")
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--real", action="store_true", help="use real_scene() instead of the demo")
    ap.add_argument("--rssi", action="store_true",
                    help="REAL motion sensing from the laptop's own WiFi RSSI (no hardware)")
    ap.add_argument("--people", type=int, default=3, help="how many demo occupants to simulate")
    ap.add_argument("--hold", type=float, default=600.0,
                    help="rssi mode: seconds after the last motion to still report 'present'")
    ap.add_argument("--hz", type=float, default=3.0, help="rssi mode: samples per second")
    args = ap.parse_args()
    DEMO = not args.real
    global N_PEOPLE
    N_PEOPLE = max(0, args.people)

    if args.rssi:
        # The detector lives in the backend package; make it importable when
        # this file is run directly as `python scripts/ruview_bridge.py`.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from backend.modules.sense.rssi_sensor import MotionDetector, diagnose, read_rssi_dbm
        first = read_rssi_dbm()
        if first is None:
            print("\n!! No WiFi signal readable. RSSI mode needs the laptop CONNECTED")
            print("   to a WiFi network (not Ethernet-only). Serving anyway — it will")
            print("   report 'not connected' until a signal appears.")
            hint = diagnose()
            if hint:
                print(f"   Likely cause: {hint}")
        else:
            print(f"\nWiFi signal found: {first:.0f} dBm — learning the quiet baseline (~15s)...")
        RSSI_LOOP = RssiLoop(MotionDetector(presence_hold_s=args.hold), hz=args.hz)
        RSSI_LOOP.start()

    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    mode = ("RSSI (real laptop-WiFi motion sensing)" if args.rssi
            else "DEMO (simulated walking skeleton)" if DEMO
            else "REAL (ruview/ESP32)")
    print(f"\nRuView bridge running — {mode}")
    print(f"  Serving http://localhost:{args.port}/api/pose  and  /api/presence")
    print("  In Plasma .env:  RUVIEW_ENABLED=true   RUVIEW_URL="
          f"http://localhost:{args.port}")
    print("  Then click '🫥 See-through (WiFi)' in Plasma.  Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
