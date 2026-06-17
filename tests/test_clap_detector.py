"""Tests for PA-99 — double-clap wake detector (pure numpy, no audio hardware)."""
from __future__ import annotations
import numpy as np
import pytest

_SR = 16_000  # 16 kHz — must match ClapDetector._SAMPLE_RATE


def _chunk(n_samples: int, amplitude: int = 100) -> np.ndarray:
    """Quiet background chunk."""
    return np.full(n_samples, amplitude, dtype=np.int16)


def _clap_chunk(n_samples: int = 1280, amplitude: int = 5000) -> np.ndarray:
    """Loud transient chunk simulating a clap."""
    c = np.zeros(n_samples, dtype=np.int16)
    c[0] = amplitude  # sharp peak at start
    return c


def _warm(detector, n_chunks: int = 30) -> None:
    """Feed quiet chunks so the baseline adapts downward to a stable level."""
    bg = _chunk(1280, amplitude=100)
    for _ in range(n_chunks):
        detector.process(bg)


# ── baseline and single events ────────────────────────────────────────────────

def test_quiet_background_no_detection():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0)
    _warm(d)
    for _ in range(50):
        r = d.process(_chunk(1280, amplitude=100))
        assert not r["detected"], "Quiet background should never trigger"


def test_single_clap_no_detection():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0)
    _warm(d)

    r = d.process(_clap_chunk())
    assert not r["detected"], "Single clap alone must not trigger"

    # After the window expires, still no detection
    gap_samples = _SR  # 1 second of silence
    for _ in range(gap_samples // 1280 + 1):
        r2 = d.process(_chunk(1280))
        assert not r2["detected"]


def test_double_clap_within_window_triggers():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800)
    _warm(d)

    # First clap
    d.process(_clap_chunk())

    # ~300 ms of silence (inside window, after min_gap)
    gap_chunks = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap_chunks):
        d.process(_chunk(1280))

    # Second clap
    result = d.process(_clap_chunk())
    assert result["detected"], "Double clap within window must trigger"
    assert result["score"] > 0


def test_double_clap_too_fast_no_detection():
    """Two claps within min_gap (< 150 ms) should NOT trigger."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800)
    _warm(d)

    # First clap
    d.process(_clap_chunk())

    # Only ~40 ms of silence (below min_gap)
    tiny_gap = max(1, (_SR * 40 // 1000) // 1280)
    for _ in range(tiny_gap):
        d.process(_chunk(1280))

    result = d.process(_clap_chunk())
    assert not result["detected"], "Too fast (< min_gap) must not trigger"


def test_double_clap_too_slow_no_detection():
    """Two claps with > max_gap between them should NOT trigger."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800)
    _warm(d)

    # First clap
    d.process(_clap_chunk())

    # 1200 ms silence — beyond max_gap of 800 ms
    long_gap = (_SR * 1200 // 1000) // 1280 + 1
    for _ in range(long_gap):
        d.process(_chunk(1280))

    result = d.process(_clap_chunk())
    assert not result["detected"], "Too slow (> max_gap) must not trigger"


def test_cooldown_prevents_immediate_retriggering():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800, cooldown_ms=1500)
    _warm(d)

    # Fire a valid double clap
    d.process(_clap_chunk())
    gap_chunks = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap_chunks):
        d.process(_chunk(1280))
    r1 = d.process(_clap_chunk())
    assert r1["detected"]

    # Immediately try another double clap — must be suppressed by cooldown
    d.process(_clap_chunk())
    for _ in range(gap_chunks):
        d.process(_chunk(1280))
    r2 = d.process(_clap_chunk())
    assert not r2["detected"], "Cooldown must suppress immediate re-detection"


def test_cooldown_expires_and_allows_next():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800, cooldown_ms=500)
    _warm(d)

    # First double clap
    d.process(_clap_chunk())
    gap = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap):
        d.process(_chunk(1280))
    r1 = d.process(_clap_chunk())
    assert r1["detected"]

    # Wait out the cooldown (600 ms > 500 ms cooldown)
    cooldown_chunks = (_SR * 600 // 1000) // 1280 + 1
    for _ in range(cooldown_chunks):
        d.process(_chunk(1280))

    # Second double clap after cooldown — should trigger
    d.process(_clap_chunk())
    for _ in range(gap):
        d.process(_chunk(1280))
    r2 = d.process(_clap_chunk())
    assert r2["detected"], "After cooldown, a new double clap must trigger"


def test_score_is_positive_on_detection():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0)
    _warm(d)

    d.process(_clap_chunk())
    gap = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap):
        d.process(_chunk(1280))
    r = d.process(_clap_chunk())
    assert r["detected"]
    assert r["score"] > 0.0


def test_reset_clears_state():
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800)
    _warm(d)

    # First clap — enters AFTER_FIRST state
    d.process(_clap_chunk())
    d.reset()

    # Now the window should be cleared; next clap is treated as a new first clap
    gap = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap):
        d.process(_chunk(1280))
    r = d.process(_clap_chunk())
    assert not r["detected"], "After reset, single clap must not trigger"


def test_baseline_adapts_to_noisy_room():
    """Detector should not trigger when background noise is consistently loud."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0)

    # Simulate a noisy room at amplitude=1000 (adapts baseline up)
    noisy_bg = _chunk(1280, amplitude=1000)
    for _ in range(100):
        d.process(noisy_bg)

    # A clap at amplitude=3000 is only 3× the noise floor (< threshold=8)
    r = d.process(_clap_chunk(amplitude=3000))
    assert not r["detected"], "Noise-adapted baseline should reject weak claps"
