"""
Camera frame capture — OpenCV (local webcam) + raw bytes decoder.

LocalCameraCapture: grabs frames from a webcam attached to the server.
decode_frame_bytes: decodes JPEG/PNG bytes (from browser or phone) into BGR numpy array.

Both return BGR numpy arrays compatible with ObjectDetector.detect().

Webcam reliability notes:
  * On Windows the default OpenCV backend (MSMF) frequently returns no frame or
    hangs on open. DirectShow (CAP_DSHOW) is far more reliable, so we try it
    first on Windows and fall back to the default backend.
  * The first frames after opening a webcam are often black/garbage while
    auto-exposure and white-balance settle — we discard a few warmup frames and
    retry the real read instead of giving up on the first failure.
"""
from __future__ import annotations
import logging
import sys
import threading
import time

import numpy as np

log = logging.getLogger("plasma.vision.capture")

# How many initial frames to read-and-discard so the sensor's auto-exposure and
# auto-white-balance settle (too few → dark or colour-cast frames).
_WARMUP_FRAMES = 8
# How many times to retry the real read before declaring failure.
_READ_RETRIES = 10
# Pause between warmup/retry reads.
_READ_DELAY_S = 0.05


def _candidate_backends():
    """Backend constants to try, most-reliable-first for this platform."""
    try:
        import cv2
    except ImportError:
        return []
    backends = []
    if sys.platform.startswith("win"):
        # DirectShow is the reliable choice on Windows.
        backends.append(getattr(cv2, "CAP_DSHOW", 700))
    backends.append(getattr(cv2, "CAP_ANY", 0))
    return backends


class LocalCameraCapture:
    """OpenCV webcam capture — single-shot or continuous."""

    def __init__(self, device_index: int = 0):
        self._device = device_index
        self._cap = None

    def open(self) -> None:
        try:
            import cv2
        except ImportError as e:
            raise ImportError("opencv-python is not installed. Run: pip install opencv-python") from e

        last_err = None
        for backend in _candidate_backends():
            try:
                cap = cv2.VideoCapture(self._device, backend)
            except Exception as e:  # pragma: no cover - backend-specific
                last_err = e
                continue
            if cap is not None and cap.isOpened():
                self._cap = cap
                # Turn ON the camera's own auto white-balance + auto-exposure so
                # colours come out natural (some webcams default these off, giving
                # a blue/green cast). Best-effort — ignored if unsupported.
                try:
                    cap.set(cv2.CAP_PROP_AUTO_WB, 1)
                except Exception:
                    pass
                log.info("Camera %s opened (backend=%s)", self._device, backend)
                return
            if cap is not None:
                cap.release()
            last_err = RuntimeError(f"backend {backend} could not open device {self._device}")
        self._cap = None
        raise RuntimeError(
            f"Cannot open camera device {self._device}. Check CAMERA_DEVICE in .env "
            f"and that no other app is using the webcam. ({last_err})"
        )

    def capture_frame(self, warmup: int = _WARMUP_FRAMES) -> np.ndarray | None:
        """Capture a single BGR frame, with warmup + retry. None on failure.

        ``warmup`` frames are read-and-discarded so auto-exposure settles. A
        camera that's already been running needs far fewer (or none), which is
        the main speed win for a kept-warm capture.
        """
        if self._cap is None:
            return None
        import cv2  # noqa: F401 — already verified in open()

        for _ in range(max(0, warmup)):
            self._cap.read()
            time.sleep(_READ_DELAY_S)

        # Now try to get a real, non-empty frame.
        for _ in range(_READ_RETRIES):
            ret, frame = self._cap.read()
            if ret and frame is not None and frame.size > 0:
                return frame
            time.sleep(_READ_DELAY_S)
        return None

    def settle(self, seconds: float) -> None:
        """Read frames for `seconds` so auto white-balance/exposure converge.

        Webcams need ~1–2 s of running before colours and brightness stabilise;
        grabbing a frame too soon gives a blue/green cast or a dark image.
        """
        if self._cap is None or seconds <= 0:
            return
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end:
            self._cap.read()
            time.sleep(_READ_DELAY_S)

    def is_open(self) -> bool:
        return self._cap is not None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()


# ── Warm camera cache — the big "find X" speed win ────────────────────────────
# Opening a webcam (esp. DirectShow on Windows) can take many seconds, and full
# warmup adds more. So we keep ONE camera open between snapshots: the first
# "find X" pays the cold-open cost, every one after is near-instant. A daemon
# timer releases the camera after CAMERA_KEEPALIVE_S of no use, so the webcam is
# freed for other apps when you're not actively using it.
_cache_lock = threading.Lock()
_cached_cam: "LocalCameraCapture | None" = None
_cached_device: int | None = None
_release_timer: "threading.Timer | None" = None


def _keepalive_seconds() -> float:
    try:
        from backend.core.config import config
        return float(getattr(config, "CAMERA_KEEPALIVE_S", 60.0))
    except Exception:
        return 60.0


def _schedule_release() -> None:
    global _release_timer
    if _release_timer is not None:
        _release_timer.cancel()
    _release_timer = threading.Timer(_keepalive_seconds(), release_camera)
    _release_timer.daemon = True
    _release_timer.start()


def release_camera() -> None:
    """Release the cached camera (called on idle timeout or shutdown)."""
    global _cached_cam, _cached_device, _release_timer
    with _cache_lock:
        if _release_timer is not None:
            _release_timer.cancel()
            _release_timer = None
        if _cached_cam is not None:
            try:
                _cached_cam.close()
            except Exception:
                pass
            log.info("Warm camera released (idle)")
        _cached_cam = None
        _cached_device = None


def snapshot(device_index: int = 0) -> np.ndarray:
    """Grab one frame, reusing a kept-warm camera. Raises if unavailable.

    First call opens the camera (slow) with full warmup; later calls reuse the
    open handle with minimal warmup, so repeated "find X" is fast.
    """
    global _cached_cam, _cached_device
    with _cache_lock:
        cold = (
            _cached_cam is None
            or _cached_device != device_index
            or not _cached_cam.is_open()
        )
        if cold:
            if _cached_cam is not None:
                try:
                    _cached_cam.close()
                except Exception:
                    pass
            cam = LocalCameraCapture(device_index)
            cam.open()                       # slow, but only on the cold path
            try:
                from backend.core.config import config
                cam.settle(float(getattr(config, "CAMERA_SETTLE_S", 1.2)))
            except Exception:
                cam.settle(1.2)
            _cached_cam = cam
            _cached_device = device_index
            warmup = _WARMUP_FRAMES           # a few more frames just before capture
        else:
            cam = _cached_cam
            warmup = 1                        # already running → barely any

        frame = cam.capture_frame(warmup=warmup)

        # A warm handle can go stale (device slept / unplugged). Reopen once.
        if frame is None and not cold:
            try:
                cam.close()
            except Exception:
                pass
            cam = LocalCameraCapture(device_index)
            cam.open()
            _cached_cam = cam
            _cached_device = device_index
            frame = cam.capture_frame(warmup=_WARMUP_FRAMES)

        _schedule_release()

    if frame is None:
        raise RuntimeError(
            "Camera returned no frame. The webcam opened but produced no image — "
            "another app may be using it, or it needs a moment to start. Try again."
        )
    return frame


def apply_gray_world(frame: np.ndarray) -> np.ndarray:
    """Gray-world auto white-balance — removes a colour cast (e.g. a blue tint
    from a webcam whose auto white-balance hasn't settled).

    Scales each BGR channel so their means match the overall grey level. Scaling
    is clamped so a genuinely colourful scene isn't over-corrected. Cheap and
    deterministic — good enough to stop "your face is blue" descriptions.
    """
    try:
        f = frame.astype(np.float32)
        means = f.reshape(-1, 3).mean(axis=0)          # B, G, R means
        gray = float(means.mean())
        if gray <= 1e-6:
            return frame
        scale = np.clip(gray / np.clip(means, 1e-6, None), 0.6, 1.6)
        f *= scale
        return np.clip(f, 0, 255).astype(np.uint8)
    except Exception:
        return frame


def decode_frame_bytes(data: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes into a BGR numpy array (from browser/phone upload)."""
    try:
        import cv2
    except ImportError as e:
        raise ImportError("opencv-python is not installed. Run: pip install opencv-python") from e
    arr = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not decode image bytes — not a valid JPEG/PNG.")
    return frame
