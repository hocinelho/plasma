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
import time

import numpy as np

log = logging.getLogger("plasma.vision.capture")

# How many initial frames to read-and-discard so the sensor settles.
_WARMUP_FRAMES = 5
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

    def capture_frame(self) -> np.ndarray | None:
        """Capture a single BGR frame, with warmup + retry. None on failure."""
        if self._cap is None:
            return None
        import cv2  # noqa: F401 — already verified in open()

        # Discard warmup frames so auto-exposure settles (ignore read result).
        for _ in range(_WARMUP_FRAMES):
            self._cap.read()
            time.sleep(_READ_DELAY_S)

        # Now try to get a real, non-empty frame.
        for _ in range(_READ_RETRIES):
            ret, frame = self._cap.read()
            if ret and frame is not None and frame.size > 0:
                return frame
            time.sleep(_READ_DELAY_S)
        return None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()


def snapshot(device_index: int = 0) -> np.ndarray:
    """Open camera, grab one frame, close. Raises RuntimeError if unavailable."""
    with LocalCameraCapture(device_index) as cam:
        frame = cam.capture_frame()
    if frame is None:
        raise RuntimeError(
            "Camera returned no frame. The webcam opened but produced no image — "
            "another app may be using it, or it needs a moment to start. Try again."
        )
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
