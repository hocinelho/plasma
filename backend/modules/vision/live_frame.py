"""The most recent frame the browser's camera sent us.

Why this exists
---------------
When the overlay or the phone is watching (`?watch=1`), the browser holds the
webcam open and streams JPEG frames to `/ws/perception-input` several times a
second. Plasma therefore already has a live picture of you.

Asking "can you see me?" used to ignore all of that and open the webcam a
second time, from Python, through DirectShow — while Chromium still had it.
Two processes contending for one device is slow even when it works: on a real
run that open took **21 seconds**, before any thinking had started.

So the vision skills look here first. A frame that arrived a moment ago is
both faster and *more* correct than one grabbed from a device someone else is
already using — it is the same camera, the same instant, no contention.

Deliberately tiny and dependency-free: it holds one decoded frame and the
time it arrived. The skill registry loads skills under synthetic module names
(see avatar_state.py for the long version), so a plain module-level global is
the one thing both sides reliably see.
"""
from __future__ import annotations

import threading
import time
from typing import Any

# How old a browser frame may be and still count as "what she can see now".
# Frames arrive at VISION_FPS (6/s by default), so anything older than this
# means the stream has stopped — the tab was closed, the camera was revoked —
# and falling back to the local webcam is the right answer.
DEFAULT_MAX_AGE_S = 3.0

_lock = threading.Lock()
_frame: Any = None
_stamp: float = 0.0


def put(frame: Any) -> None:
    """Record a frame that just arrived from a browser camera."""
    global _frame, _stamp
    with _lock:
        _frame = frame
        _stamp = time.monotonic()


def get(max_age_s: float = DEFAULT_MAX_AGE_S) -> Any:
    """The latest browser frame, or None if there isn't a fresh one.

    Returns the frame itself, not a copy: callers read it, and copying a
    720p array on every call would cost more than it protects against.
    """
    with _lock:
        if _frame is None or (time.monotonic() - _stamp) > max_age_s:
            return None
        return _frame


def age_s() -> float | None:
    """Seconds since the last frame arrived, or None if none ever has.

    For logging: "used the browser's camera (0.2s old)" is the line that
    explains an answer arriving instantly instead of half a minute later.
    """
    with _lock:
        return None if _frame is None else time.monotonic() - _stamp


def clear() -> None:
    """Forget the current frame — the stream stopped, or a test is ending."""
    global _frame, _stamp
    with _lock:
        _frame = None
        _stamp = 0.0
