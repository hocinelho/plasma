"""
Floor plan + room mapping for WiFi sensing.

You describe your home as rooms (rectangles in a normalised 0..1 space, per
floor); this maps a person's estimated (x, y) position — which real RuView
deployments get by trilaterating multiple ESP32 nodes — to a room and floor.

Edit `.plasma/floorplan.json` to match your home; a sample plan is used if it's
missing. Coordinates are 0..1 (fractions of the plan width/height).

Format:
    {
      "floors": [
        {"name": "Ground", "level": 0, "rooms": [
            {"name": "living room", "x": 0.0, "y": 0.0, "w": 0.55, "h": 0.6},
            {"name": "kitchen",     "x": 0.55,"y": 0.0, "w": 0.45, "h": 0.4},
            {"name": "hallway",     "x": 0.0, "y": 0.6, "w": 1.0,  "h": 0.4}
        ]}
      ]
    }
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger("plasma.sense.floorplan")

DEFAULT_FLOORPLAN = {
    "floors": [
        {
            "name": "Ground floor",
            "level": 0,
            "rooms": [
                {"name": "living room", "x": 0.00, "y": 0.00, "w": 0.55, "h": 0.55},
                {"name": "kitchen",     "x": 0.55, "y": 0.00, "w": 0.45, "h": 0.40},
                {"name": "bathroom",    "x": 0.55, "y": 0.40, "w": 0.45, "h": 0.20},
                {"name": "hallway",     "x": 0.00, "y": 0.55, "w": 1.00, "h": 0.20},
                {"name": "entrance",    "x": 0.00, "y": 0.75, "w": 1.00, "h": 0.25},
            ],
        },
        {
            "name": "Upstairs",
            "level": 1,
            "rooms": [
                {"name": "bedroom",  "x": 0.00, "y": 0.00, "w": 0.55, "h": 0.60},
                {"name": "office",   "x": 0.55, "y": 0.00, "w": 0.45, "h": 0.60},
                {"name": "landing",  "x": 0.00, "y": 0.60, "w": 1.00, "h": 0.40},
            ],
        },
    ]
}


def _plan_path():
    from backend.core.config import config
    return config.PLASMA_DIR / "floorplan.json"


def load_floorplan() -> dict:
    """Return the user's floor plan, or the built-in sample if none exists."""
    try:
        p = _plan_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("floorplan: could not read %s (%s) — using default", _plan_path(), e)
    return DEFAULT_FLOORPLAN


def _in_rect(x: float, y: float, r: dict) -> bool:
    return r["x"] <= x < r["x"] + r["w"] and r["y"] <= y < r["y"] + r["h"]


def room_for(x: float, y: float, level: Optional[int] = None, plan: Optional[dict] = None) -> dict:
    """Map (x, y) [0..1] on floor `level` to {"room", "floor", "level"} (or empties)."""
    plan = plan or load_floorplan()
    floors = plan.get("floors", [])
    candidates = [f for f in floors if level is None or f.get("level") == level] or floors
    for fl in candidates:
        for r in fl.get("rooms", []):
            if _in_rect(x, y, r):
                return {"room": r["name"], "floor": fl.get("name", ""), "level": fl.get("level", 0)}
    return {"room": "", "floor": candidates[0].get("name", "") if candidates else "", "level": level or 0}
