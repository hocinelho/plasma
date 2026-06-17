"""
Camera frame capture — OpenCV (local webcam) + raw bytes decoder.

LocalCameraCapture: grabs frames from a webcam attached to the server.
decode_frame_bytes: decodes JPEG/PNG bytes (from browser or phone) into BGR numpy array.

Both return BGR numpy arrays compatible with ObjectDetector.detect().
"""
from __future__ import annotations
import logging

import numpy as np

log = logging.getLogger("plasma.vision.capture")


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
        self._cap = cv2.VideoCapture(self._device)
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Cannot open camera device {self._device}. Check CAMERA_DEVICE in .env.")

    def capture_frame(self) -> np.ndarray | None:
        """Capture a single BGR frame. Returns None on read failure."""
        if self._cap is None:
            return None
        import cv2  # noqa: F401 — already verified in open()
        ret, frame = self._cap.read()
        return frame if ret else None

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
        raise RuntimeError("Camera returned no frame.")
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
