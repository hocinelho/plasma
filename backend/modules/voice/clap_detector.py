"""
Double-clap wake detector — pure-numpy DSP, no ML model required.

Algorithm:
  1. Maintain adaptive background RMS via slow EMA (quiet room baseline)
  2. Detect a transient when chunk peak > threshold × background_rms
  3. State machine:
       IDLE → AFTER_FIRST (first clap hit)
       AFTER_FIRST → COOLDOWN (second clap within [min_gap, max_gap] ms → detected!)
       AFTER_FIRST → IDLE   (window expired, no second clap)
       COOLDOWN → IDLE      (suppression period over)

Same process() interface as WakeWordDetector so WakeMonitor can run both.
"""
from __future__ import annotations
import enum
import logging

import numpy as np

log = logging.getLogger("plasma.clap")

_SAMPLE_RATE = 16_000  # must match AudioCapture


class _State(enum.Enum):
    IDLE = "idle"
    AFTER_FIRST = "after_first"
    COOLDOWN = "cooldown"


class ClapDetector:
    """Double-clap detector with the same process() interface as WakeWordDetector."""

    def __init__(
        self,
        threshold: float = 8.0,
        min_gap_ms: int = 150,
        max_gap_ms: int = 800,
        cooldown_ms: int = 1500,
    ):
        self._threshold = threshold
        self._min_gap = min_gap_ms * _SAMPLE_RATE // 1000
        self._max_gap = max_gap_ms * _SAMPLE_RATE // 1000
        self._cooldown = cooldown_ms * _SAMPLE_RATE // 1000

        # Adaptive background: EMA of chunk RMS; 300 = typical quiet room
        self._bg_rms: float = 300.0
        self._bg_alpha: float = 0.01  # slow decay keeps baseline stable against noise bursts

        self._state: _State = _State.IDLE
        self._state_samples: int = 0
        self._first_score: float = 0.0

    # ── public API ────────────────────────────────────────────────────────

    def process(self, chunk: np.ndarray) -> dict:
        """
        Process one int16 audio chunk (shape: (N,)).
        Returns {"detected": bool, "score": float}.
        score = average clap-to-background ratio (higher = louder / cleaner clap pair).
        """
        n = len(chunk)
        peak = float(np.abs(chunk).max())
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        is_transient = peak > self._bg_rms * self._threshold

        detected = False
        score = 0.0

        if self._state is _State.IDLE:
            if is_transient:
                self._state = _State.AFTER_FIRST
                self._state_samples = 0
                self._first_score = peak / (self._bg_rms + 1e-6)
                log.debug("Clap: first transient (score=%.1f)", self._first_score)
            else:
                # Only update background during silence to avoid noise drift
                self._bg_rms = (1 - self._bg_alpha) * self._bg_rms + self._bg_alpha * rms

        elif self._state is _State.AFTER_FIRST:
            if is_transient:
                # Check gap BEFORE adding n so chunk-boundary doesn't inflate the count.
                if self._state_samples >= self._min_gap and self._state_samples <= self._max_gap:
                    # Perfect gap — second clap!
                    score = (self._first_score + peak / (self._bg_rms + 1e-6)) / 2
                    detected = True
                    self._state = _State.COOLDOWN
                    self._state_samples = 0
                    log.info("Double clap detected! score=%.1f", score)
                else:
                    # Too fast (< min_gap) or too slow (> max_gap) — reset; treat as new first clap
                    self._state_samples = 0
                    self._first_score = peak / (self._bg_rms + 1e-6)
                    log.debug("Clap: bad gap (%d samples), reset to first clap", self._state_samples)
            else:
                # Quiet chunk — advance the elapsed timer
                self._state_samples += n
                if self._state_samples > self._max_gap:
                    # Window expired with no second clap
                    self._state = _State.IDLE
                    self._state_samples = 0
                    log.debug("Clap: window expired, reset")

        elif self._state is _State.COOLDOWN:
            self._state_samples += n
            if self._state_samples >= self._cooldown:
                self._state = _State.IDLE
                self._state_samples = 0
                log.debug("Clap: cooldown over")

        return {"detected": detected, "score": score}

    def reset(self) -> None:
        self._state = _State.IDLE
        self._state_samples = 0
        self._first_score = 0.0
        log.debug("ClapDetector reset")
