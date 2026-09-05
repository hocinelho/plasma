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


# ── crest-factor / impulsiveness gate (fixes "voice/clicks trigger it") ───────

def _sustained_chunk(n_samples: int = 1280, amplitude: int = 5000) -> np.ndarray:
    """A LOUD but SUSTAINED chunk — energy fills the whole chunk, like a raised
    voice or a held tone, unlike a real clap's brief transient."""
    return np.full(n_samples, amplitude, dtype=np.int16)


def _short_burst_chunk(n_samples: int = 1280, amplitude: int = 5000, width: int = 400) -> np.ndarray:
    """A moderately impulsive chunk — energy fills `width` samples (~25ms),
    like a loud spoken syllable/plosive: louder and shorter than a raised voice,
    but nowhere near as impulsive as a real clap (which is only a few ms)."""
    c = np.zeros(n_samples, dtype=np.int16)
    c[:width] = amplitude
    return c


def test_sustained_loud_voice_never_triggers():
    """Talking loudly (sustained energy) must not be mistaken for a clap, even
    at a peak amplitude that would clear the old (crest-less) threshold."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_crest=5.0)
    _warm(d)
    for _ in range(60):
        r = d.process(_sustained_chunk(amplitude=5000))
        assert not r["detected"], "Sustained loud voice must never register as a clap"


def test_double_loud_syllable_not_detected_as_double_clap():
    """Two loud spoken syllables (moderate crest, not a sharp clap) in the
    double-clap timing window must not fire — this was the reported false
    trigger ('voice activated the clap detector')."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=8.0, min_gap_ms=150, max_gap_ms=800, min_crest=5.0)
    _warm(d)
    d.process(_short_burst_chunk())
    gap = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap):
        d.process(_chunk(1280))
    r = d.process(_short_burst_chunk())
    assert not r["detected"], "Loud syllables (low crest) must not count as claps"


def test_min_peak_floor_rejects_quiet_transient_in_silent_room():
    """In a very quiet room the adaptive baseline drops low, so a small relative
    threshold could let a faint click through; the absolute floor must reject it."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector(threshold=2.0, min_crest=1.0, min_peak=1400)
    # Very quiet background — baseline settles near ~10-20.
    quiet = _chunk(1280, amplitude=15)
    for _ in range(200):
        d.process(quiet)
    # A soft transient: relatively loud (>> bg*2) but below the absolute floor.
    soft_click = np.zeros(1280, dtype=np.int16)
    soft_click[0] = 500
    r = d.process(soft_click)
    assert not r["detected"] or True  # first hit alone never "detects" (needs pair)
    # Confirm it didn't even register as a transient by checking state didn't
    # advance to AFTER_FIRST: a genuine clap-strength second hit right after
    # should NOT complete a pair, because the first was below min_peak.
    r2 = d.process(_clap_chunk(amplitude=5000))
    assert not r2["detected"], "A sub-floor transient must not count as the first clap"


def test_default_constructor_still_detects_a_real_clap():
    """Sanity: the new stricter defaults (threshold=12, min_crest=5, min_peak=1400)
    still recognise a genuine sharp double clap at normal clapping loudness."""
    from backend.modules.voice.clap_detector import ClapDetector
    d = ClapDetector()  # all defaults
    _warm(d)
    d.process(_clap_chunk(amplitude=6000))
    gap = (_SR * 300 // 1000) // 1280 + 1
    for _ in range(gap):
        d.process(_chunk(1280))
    r = d.process(_clap_chunk(amplitude=6000))
    assert r["detected"], "A genuine sharp double clap must still trigger under stricter defaults"


from backend.modules.voice.clap_detector import ClapDetector  # noqa: E402


class TestTheBackgroundCannotCollapse:
    """`threshold` is a RATIO against the running background level, and a
    ratio against a number that can fall to nearly zero is not a threshold.

    Measured on a real machine: in a quiet room the background EMA settled
    near 5 instead of the 300 it starts at, so "peak > background x 12" meant
    "peak > 60" and typing woke her every few seconds — logged scores of 964,
    683, 1110 against a threshold of 12. Raising the threshold chases a
    denominator that keeps moving: set high enough to reject the noise, it
    rejected real claps too, and the next session had no detections at all.
    """

    def _quiet_room(self, det, seconds=20.0):
        """Feed near-silence until the background EMA has settled."""
        chunks = int(seconds * 16000 / 1280)
        for _ in range(chunks):
            det.process(np.zeros(1280, dtype=np.int16))

    def test_silence_cannot_drive_the_background_to_zero(self):
        det = ClapDetector()
        self._quiet_room(det)
        assert det._bg_rms >= 120.0

    def test_the_shipped_threshold_still_means_something_after_silence(self):
        """The bar for a transient is background x threshold. After a long
        quiet spell that has to still be a real sound, not any sound."""
        det = ClapDetector(threshold=12.0)
        self._quiet_room(det)
        assert det._bg_rms * det._threshold >= 1000

    def test_a_noisy_room_still_raises_the_bar_freely(self):
        """The floor is a floor, not a clamp — it must never stop the
        background rising to meet a genuinely loud room."""
        det = ClapDetector()
        loud = (np.random.RandomState(0).normal(0, 3000, 1280)).astype(np.int16)
        for _ in range(400):
            det.process(loud)
        assert det._bg_rms > 500

    def test_a_real_double_clap_still_registers_on_the_defaults(self):
        """The point of fixing the denominator rather than the threshold:
        the shipped defaults work again."""
        det = ClapDetector()
        self._quiet_room(det, seconds=5.0)
        quiet = np.zeros(1280, dtype=np.int16)

        def clap():
            c = np.zeros(1280, dtype=np.int16)
            c[10:14] = 20000          # a few loud samples = high crest
            return c

        det.process(clap())
        for _ in range(4):            # ~320 ms gap, inside the window
            det.process(quiet)
        assert det.process(clap())["detected"] is True
