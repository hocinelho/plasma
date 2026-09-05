"""
Double-clap wake detector — pure-numpy DSP, no ML model required.

Algorithm:
  1. Maintain adaptive background RMS via slow EMA (quiet room baseline)
  2. Detect a transient when ALL of:
       a) chunk peak > threshold × background_rms   (loud relative to the room)
       b) chunk peak > min_peak                      (loud in absolute terms —
          stops a very quiet room from making tiny sounds "relatively loud")
       c) crest factor (peak / chunk RMS) > min_crest (IMPULSIVE, not sustained)
     (c) is what stops normal talking from being mistaken for a clap: a clap's
     energy is concentrated in a few ms within the ~80 ms analysis chunk, so the
     chunk's peak-to-RMS ratio is very high; sustained speech fills the whole
     chunk, so its peak-to-RMS ratio is much lower even at the same peak volume.
  3. State machine:
       IDLE → AFTER_FIRST (first clap hit)
       AFTER_FIRST → COOLDOWN (second clap within [min_gap, max_gap] ms → detected!)
       AFTER_FIRST → IDLE   (window expired, no second clap)
       COOLDOWN → IDLE      (suppression period over)

If clicks (mouse/keyboard) near the microphone still false-trigger, they are
physically impulsive too — raise CLAP_THRESHOLD and/or CLAP_MIN_PEAK so only
sounds genuinely as loud as a clap (not a soft click) pass the amplitude gate.

Same process() interface as WakeWordDetector so WakeMonitor can run both.
"""
from __future__ import annotations
import enum
import logging

import numpy as np

log = logging.getLogger("plasma.clap")

_SAMPLE_RATE = 16_000  # must match AudioCapture

# Floor under the adaptive background level.
#
# `threshold` is a RATIO — a transient counts when its peak is `threshold`
# times the running background RMS — and a ratio against a number that can
# fall to nearly zero is not a threshold at all. In a quiet room, with a good
# mic, the background EMA settled around 5 rather than the 300 it starts at,
# so `peak > bg * 12` came out as `peak > 60`: everything qualified. Real logs
# showed scores of 964, 683, 1110 against a threshold of 12, and typing was
# waking her every few seconds.
#
# Raising `threshold` looks like the fix and is not: it chases a denominator
# that keeps moving, and set high enough to reject noise it also rejects real
# claps, which is exactly what happened next — an entire session with no
# detections at all. Flooring the denominator makes the ratio mean the same
# thing in every room, so the shipped default works again.
#
# 120 is below the RMS of a genuinely quiet room recorded at normal gain, so
# it never *raises* the bar in a noisy one — the EMA still floats up freely.
_BG_RMS_FLOOR = 120.0


class _State(enum.Enum):
    IDLE = "idle"
    AFTER_FIRST = "after_first"
    COOLDOWN = "cooldown"


class ClapDetector:
    """Double-clap detector with the same process() interface as WakeWordDetector."""

    def __init__(
        self,
        threshold: float = 12.0,
        min_gap_ms: int = 150,
        max_gap_ms: int = 800,
        cooldown_ms: int = 1500,
        min_crest: float = 5.0,
        min_peak: int = 1400,
    ):
        self._threshold = threshold
        self._min_gap = min_gap_ms * _SAMPLE_RATE // 1000
        self._max_gap = max_gap_ms * _SAMPLE_RATE // 1000
        self._cooldown = cooldown_ms * _SAMPLE_RATE // 1000
        # Impulsiveness gate: real claps are short (a few ms) inside an ~80 ms
        # chunk, so peak/RMS is high; sustained talking fills the chunk, so
        # peak/RMS is much lower even at the same peak loudness.
        self._min_crest = min_crest
        # Absolute loudness floor so a very quiet room's low baseline doesn't
        # make faint sounds (e.g. a soft click) count as "relatively loud".
        self._min_peak = min_peak

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
        crest = peak / (rms + 1e-6)
        is_transient = (
            peak > self._bg_rms * self._threshold
            and peak > self._min_peak
            and crest > self._min_crest
        )

        detected = False
        score = 0.0

        if self._state is _State.IDLE:
            if is_transient:
                self._state = _State.AFTER_FIRST
                self._state_samples = 0
                self._first_score = peak / (self._bg_rms + 1e-6)
                log.debug("Clap: first transient (score=%.1f)", self._first_score)
            else:
                # Only update background during silence to avoid noise drift.
                # Floored, because everything below is a ratio against it —
                # see _BG_RMS_FLOOR for what a collapsed denominator did.
                self._bg_rms = max(
                    _BG_RMS_FLOOR,
                    (1 - self._bg_alpha) * self._bg_rms + self._bg_alpha * rms,
                )

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
