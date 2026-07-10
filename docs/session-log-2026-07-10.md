# Session Log — 2026-07-10

> Level 1 real WiFi sensing (laptop RSSI motion detection), the Windows 11
> location-services blocker, and the plan for the vision detection upgrade.
> Branch: `claude/session-015ndjdsamrc9cy69awrrpeb-x6de9z` → PR #2 into
> `claude/enhance-plasma-project-cOZli`.

---

## 1. Context: from fake demo to real sensing

All WiFi sensing so far ran on `ruview_bridge.py`'s simulated demo scene.
Hocine asked what real hardware could do. Findings:

- His **Teltonika TRB500** gateway is 5G-only — no WiFi radio, unusable as a
  sensor. Its cellular metrics (RSRP/SINR) measure the tower link, not people.
- His laptop (Intel Wi-Fi 6E AX211) **can't expose CSI on Windows** — no
  driver support. But it can read its own RSSI, whose jitter reveals motion.
- Agreed ladder: **Level 1** = laptop RSSI motion sensing (no hardware, this
  session) → **Level 2** = ESP32-S3 + ESP-CSI into `real_scene()` (real
  through-wall presence/breathing; hardware not ordered yet).

## 2. Level 1 implementation (PR #2)

**`backend/modules/sense/rssi_sensor.py`** — pure stdlib:
- `read_rssi_dbm()`: `netsh wlan show interfaces` on Windows (percent → dBm,
  localization-tolerant: tested with English + German output),
  `/proc/net/wireless` on Linux.
- `MotionDetector`: sliding window (8 s) standard deviation vs an adaptive
  quiet baseline (EWMA learned while calm) with an absolute floor
  (`min_sigma_db=0.8`), safety factor `k=3`, 15 s warm-up. A still person is
  invisible to RSSI, so `present` = motion within `presence_hold_s` (600 s).
  Time injected everywhere → fully unit-testable, no sleeps.

**`scripts/ruview_bridge.py --rssi [--hold s] [--hz n]`** — third mode next to
demo/real. Daemon thread feeds the detector ~3×/s; serves the same
`/api/presence` + `/api/pose` endpoints, so `wifi_sense`, RuViewMonitor
alerts, and the UI work unchanged. Honest scene: count 0/1, no rooms, no
pose, no vitals, plus diagnostics (`connected`, `warming_up`, `motion_level`,
`rssi_dbm`, `sigma_db`, `threshold_db`).

**Tests:** `tests/test_rssi_sensor.py`, 11 tests — parsers, quiet-room
negative, motion + presence hold/decay, warm-up gating, disconnected
handling, status-shape contract. Full sense suite green (22 passed).

## 3. Real-world test → blocked by company policy

On Hocine's machine `netsh wlan show interfaces` returned (German Windows):

> „Netzwerkshellbefehle benötigen Standortberechtigungen … Aktivieren Sie
> Positionsdienste“ / „WlanQueryInterface gibt den Fehler 5 zurück“

**Windows 11 24H2 hides WLAN details (incl. Signal %) unless Location
Services are enabled or the shell is elevated.** It's a company laptop —
location services can't be enabled. Options left untested: run the bridge
from an **Administrator PowerShell**, use a private machine, or the
phone-hotspot test (laptop on phone hotspot, phone across the room).

Follow-up commit: the bridge now detects this exact netsh notice at startup
(`netsh_blocker_hint()` / `diagnose()` in `rssi_sensor.py`) and prints the
fix instead of the generic "no WiFi signal" warning.

**Status: Level 1 is code-complete + unit-tested, NOT yet live-tested.**

## 4. Repo hygiene found along the way

- Old `main` still carries a real Groq key in `.env.example` → revoke at
  console.groq.com (unconfirmed as of today).
- A local-only WIP commit (`2923ce0`) on Hocine's machine added 60 MB
  `voices/*.onnx` + `external/locate-anything.cpp` as an embedded git repo —
  advised `git reset --soft HEAD~1` and gitignoring both. Confirm it never
  got pushed.

## 5. Next: vision detection upgrade

Hocine is **not satisfied with the current detection quality**. Next planned
work: integrate his fork of Roboflow Supervision
(**https://github.com/hocinelho/supervision** — detection post-processing,
ByteTrack tracking, annotation, zone/line tools) into
`backend/modules/vision/` (`detector.py`, `tracker.py`). Read
`docs/locate-vision-status.md` first for the current vision state.
