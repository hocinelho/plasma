"""
Plasma global hotkey daemon — hold F9 to talk to Plasma from anywhere in Windows.

Records mic audio while F9 is held. On release, transcribes and sends to /chat.
Prints the transcript and reply in the terminal.

Uses the 'keyboard' pip package. On Windows this does NOT require admin rights.

Run with:
    python -m backend.modules.voice.hotkey
"""
from __future__ import annotations
import logging
import sys
import threading
import time
from typing import List

import httpx
import keyboard
import numpy as np

from backend.modules.voice.audio_capture import AudioCapture, SAMPLE_RATE
from backend.modules.voice.pipeline import transcribe_array

HOTKEY = "f9"
SERVER_URL = "http://127.0.0.1:8000"
SESSION_ID = "hotkey-desktop"

log = logging.getLogger("plasma.hotkey")


class HotkeyDaemon:
    def __init__(self):
        self.capture = AudioCapture()
        self._buf: List[np.ndarray] = []
        self._recording = False
        self._record_start = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        self.capture.start()
        keyboard.on_press_key(HOTKEY, self._on_press, suppress=False)
        keyboard.on_release_key(HOTKEY, self._on_release, suppress=False)
        print(f"\nPlasma hotkey daemon running. Hold [{HOTKEY.upper()}] to talk.\n", flush=True)
        print("Press Ctrl+C to quit.\n", flush=True)

        # Background thread that drains the mic queue into our buffer while recording
        threading.Thread(target=self._mic_drain_loop, daemon=True).start()

        # Keep main thread alive
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.capture.stop()

    def _mic_drain_loop(self) -> None:
        while True:
            chunk = self.capture.get_chunk(timeout=0.5)
            if chunk is None:
                continue
            with self._lock:
                if self._recording:
                    self._buf.append(chunk)

    def _on_press(self, _event) -> None:
        with self._lock:
            if self._recording:
                return
            self._buf = []
            self._recording = True
            self._record_start = time.time()
        print(f"[{self._record_start:.0f}] Recording...", flush=True)

    def _on_release(self, _event) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            audio = np.concatenate(self._buf) if self._buf else np.array([], dtype=np.int16)
            self._buf = []

        duration = len(audio) / SAMPLE_RATE if len(audio) else 0.0
        print(f"  Captured {duration:.2f}s", flush=True)

        if duration < 0.2:
            print("  Too short — ignored.\n", flush=True)
            return

        threading.Thread(
            target=self._process_audio,
            args=(audio,),
            daemon=True,
        ).start()

    def _process_audio(self, audio: np.ndarray) -> None:
        print("  Transcribing...", flush=True)
        t0 = time.time()
        asr = transcribe_array(audio)
        text = asr.get("text", "").strip()
        lat_asr = time.time() - t0
        if not text:
            print(f"  (no speech detected, asr_lat={lat_asr:.1f}s)\n", flush=True)
            return

        print(f"  You said: \"{text}\"  (asr={lat_asr:.1f}s)", flush=True)
        print("  Plasma is thinking...", flush=True)

        try:
            t0 = time.time()
            r = httpx.post(
                f"{SERVER_URL}/chat",
                json={"session_id": SESSION_ID, "message": text},
                timeout=120.0,
            )
            r.raise_for_status()
            reply = r.json().get("reply", "")
            lat_llm = time.time() - t0
            print(f"  Plasma: \"{reply}\"  (llm={lat_llm:.1f}s)\n", flush=True)
        except Exception as e:
            print(f"  Error calling /chat: {e}\n", flush=True)


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,  # reduce noise; we use prints
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    daemon = HotkeyDaemon()
    daemon.start()


if __name__ == "__main__":
    main()