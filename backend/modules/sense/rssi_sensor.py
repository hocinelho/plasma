"""
Laptop WiFi RSSI motion sensing — "Level 1" real sensing, no extra hardware.

A person moving between the laptop and the WiFi access point disturbs the
radio path, which shows up as jitter in the received signal strength (RSSI).
This module reads the laptop's own RSSI (netsh on Windows, /proc/net/wireless
on Linux) and turns that jitter into motion / presence readings.

Honest limits (vs. real CSI on an ESP32-S3):
  • it detects MOTION only — a person sitting still is invisible, so
    "present" means "motion seen within the last presence_hold_s seconds"
  • house-level only: no rooms, count is 0 or 1, no pose, no vitals
  • the laptop must be CONNECTED to a WiFi network

Detection: keep a short sliding window of RSSI samples; motion = the window's
standard deviation exceeding an adaptive quiet baseline (learned while calm)
by a safety factor. Pure standard library; used by scripts/ruview_bridge.py.
"""
from __future__ import annotations

import logging
import re
import statistics
import subprocess
import sys
import time
from collections import deque
from typing import Optional

log = logging.getLogger("plasma.sense.rssi")

# netsh reports signal as a percentage; Windows maps it linearly to dBm.
_PCT_RE = re.compile(r"(\d{1,3})\s*%")


def percent_to_dbm(pct: float) -> float:
    """Windows WLAN quality percent → dBm (linear map: 0% = -100, 100% = -50)."""
    return pct / 2.0 - 100.0


def parse_netsh_signal(text: str) -> Optional[float]:
    """Extract the signal strength (dBm) from `netsh wlan show interfaces` output.

    Localized Windows keeps the word "Signal" in most languages (en/de at
    least); fall back to the first standalone percentage anywhere.
    """
    fallback = None
    for line in text.splitlines():
        m = _PCT_RE.search(line)
        if not m:
            continue
        pct = int(m.group(1))
        if pct > 100:
            continue
        if "signal" in line.lower():
            return percent_to_dbm(pct)
        if fallback is None:
            fallback = percent_to_dbm(pct)
    return fallback


def parse_proc_wireless(text: str) -> Optional[float]:
    """Extract the level (dBm) from /proc/net/wireless contents."""
    for line in text.splitlines():
        if ":" not in line:
            continue
        fields = line.split()
        if len(fields) >= 4:
            try:
                return float(fields[3].rstrip("."))
            except ValueError:
                continue
    return None


def read_rssi_dbm() -> Optional[float]:
    """Read the current WiFi RSSI in dBm, or None if not connected/available."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=4.0,
            ).stdout
            return parse_netsh_signal(out)
        with open("/proc/net/wireless", encoding="utf-8") as f:
            return parse_proc_wireless(f.read())
    except Exception as e:
        log.debug("RSSI read failed: %s", e)
        return None


class MotionDetector:
    """Turn a stream of RSSI samples into motion / presence.

    Feed samples with add_sample(); read the current state from status().
    All timing is passed in explicitly (or defaults to time.time()) so the
    logic is fully unit-testable without sleeping.
    """

    def __init__(
        self,
        window_s: float = 8.0,
        min_sigma_db: float = 0.8,
        k: float = 3.0,
        presence_hold_s: float = 600.0,
        warmup_s: float = 15.0,
    ):
        self.window_s = window_s
        self.min_sigma_db = min_sigma_db      # absolute jitter floor to call motion
        self.k = k                            # motion = sigma > k × quiet baseline
        self.presence_hold_s = presence_hold_s
        self.warmup_s = warmup_s
        self._samples: deque[tuple[float, float]] = deque()
        self._baseline_db: Optional[float] = None  # EWMA of sigma while quiet
        self._first_t: Optional[float] = None
        self._last_motion_t: Optional[float] = None
        self._connected = False

    # ── feeding ───────────────────────────────────────────────────────────

    def add_sample(self, rssi_dbm: Optional[float], t: Optional[float] = None) -> dict:
        t = time.time() if t is None else t
        self._connected = rssi_dbm is not None
        if rssi_dbm is not None:
            if self._first_t is None:
                self._first_t = t
            self._samples.append((t, rssi_dbm))
            cutoff = t - self.window_s
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()
            self._update(t)
        return self.status(t)

    def _sigma(self) -> Optional[float]:
        if len(self._samples) < 5:
            return None
        return statistics.pstdev(s for _, s in self._samples)

    def _threshold(self) -> float:
        base = self._baseline_db if self._baseline_db is not None else 0.0
        return max(self.min_sigma_db, self.k * base)

    def _update(self, t: float) -> None:
        sigma = self._sigma()
        if sigma is None:
            return
        warming = (t - self._first_t) < self.warmup_s
        quiet = sigma <= self._threshold()
        if warming or quiet:
            # Learn the quiet noise floor only while calm (or settling in).
            self._baseline_db = (
                sigma if self._baseline_db is None
                else 0.95 * self._baseline_db + 0.05 * sigma
            )
        elif not warming:
            self._last_motion_t = t

    # ── reading ───────────────────────────────────────────────────────────

    def status(self, t: Optional[float] = None) -> dict:
        t = time.time() if t is None else t
        sigma = self._sigma()
        threshold = self._threshold()
        warming = self._first_t is not None and (t - self._first_t) < self.warmup_s
        motion = (
            not warming and sigma is not None and sigma > threshold
        )
        last_ago = None if self._last_motion_t is None else t - self._last_motion_t
        present = last_ago is not None and last_ago <= self.presence_hold_s
        return {
            "ok": True,
            "connected": self._connected,
            "warming_up": bool(warming),
            "motion": bool(motion),
            "motion_level": round(min(sigma / threshold, 3.0), 2) if sigma else 0.0,
            "present": bool(present),
            "rssi_dbm": self._samples[-1][1] if self._samples else None,
            "sigma_db": round(sigma, 2) if sigma is not None else None,
            "threshold_db": round(threshold, 2),
            "baseline_db": round(self._baseline_db, 2) if self._baseline_db is not None else None,
            "last_motion_ago_s": round(last_ago, 1) if last_ago is not None else None,
            "samples": len(self._samples),
        }
