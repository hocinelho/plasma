"""Turning a raw per-frame reading into a single, well-timed reaction.

The camera runs at a few frames a second. Fed straight through, "is a hand
raised" fires a reaction on every single frame for as long as the hand stays
up, and a one-frame misdetection fires it when nothing was really meant. Both
faults already existed ad hoc in the perception handler for the greeting and
sleepy-alert reactions; this gives the pattern a name, a test, and a place to
reuse it without copying the same two counters again.
"""
from __future__ import annotations


class DebouncedTrigger:
    """Fires once a condition has held for N consecutive observations, then
    withholds further fires for a cooldown period.

    Not fed real time by itself — `now` is passed in on every call, so it can
    be driven by `time.monotonic()` in production and by a fake clock in
    tests without patching anything global.
    """

    def __init__(self, frames: int, cooldown_s: float) -> None:
        self.frames_needed = max(1, int(frames))
        self.cooldown_s = float(cooldown_s)
        self._streak = 0
        self._last_fired = float("-inf")

    def observe(self, condition: bool, now: float) -> bool:
        """Feed one frame's reading. True exactly on the frame that should
        fire the reaction — never twice in a row for the same held condition."""
        if not condition:
            self._streak = 0
            return False
        self._streak += 1
        if self._streak < self.frames_needed:
            return False
        if (now - self._last_fired) < self.cooldown_s:
            return False
        self._last_fired = now
        self._streak = 0     # the condition must build up fresh for the next fire
        return True

    def reset(self) -> None:
        """Drop the streak without touching the cooldown — used when the
        condition becomes meaningless for a moment (e.g. the hand briefly
        left the frame) rather than genuinely absent."""
        self._streak = 0
