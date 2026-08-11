"""Meeting recorder — listens through a meeting and builds a transcript.

Runs its own microphone stream in a background thread, batches the audio into
segments and transcribes each with Whisper as the meeting goes on, so a long
meeting never has to be transcribed in one huge pass at the end.

Every finished segment is appended to a JSONL file under
`.plasma/meetings/` *as it happens*, so an hour of meeting survives a crash,
a reload or someone closing the laptop lid.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from backend.core.config import config

log = logging.getLogger("plasma.meeting")

SAMPLE_RATE = 16_000
# Whisper is far more accurate on a sentence or two than on 1-second slivers,
# but long segments delay the live transcript. ~25 s is a good middle.
SEGMENT_SECONDS = 25
# Below this RMS a segment is treated as silence and never sent to Whisper —
# it would otherwise hallucinate text out of room noise.
SILENCE_RMS = 120.0

MEETINGS_DIR: Path = config.PLASMA_DIR / "meetings"


@dataclass
class MeetingState:
    meeting_id: str
    title: str
    started_at: datetime
    ended_at: datetime | None = None
    segments: list[dict] = field(default_factory=list)

    @property
    def transcript(self) -> str:
        return "\n".join(s["text"] for s in self.segments if s.get("text"))

    @property
    def duration_min(self) -> float:
        end = self.ended_at or datetime.now()
        return max(0.0, (end - self.started_at).total_seconds() / 60.0)

    def path(self) -> Path:
        return MEETINGS_DIR / f"{self.meeting_id}.jsonl"


class MeetingRecorder:
    """Records and transcribes one meeting at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state: MeetingState | None = None
        self._error: str | None = None

    # ── status ────────────────────────────────────────────────────────────
    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        with self._lock:
            st = self._state
            return {
                "recording": self.is_recording,
                "meeting_id": st.meeting_id if st else None,
                "title": st.title if st else None,
                "segments": len(st.segments) if st else 0,
                "duration_min": round(st.duration_min, 1) if st else 0.0,
                "error": self._error,
            }

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self, title: str | None = None) -> MeetingState:
        """Begin recording. Raises RuntimeError if one is already running."""
        if self.is_recording:
            raise RuntimeError("A meeting is already being recorded.")

        now = datetime.now()
        state = MeetingState(
            meeting_id=now.strftime("%Y%m%d-%H%M%S"),
            title=(title or "").strip() or f"Meeting {now.strftime('%d.%m.%Y %H:%M')}",
            started_at=now,
        )
        MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._state = state
            self._error = None
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="meeting-recorder", daemon=True
        )
        self._thread.start()
        log.info("Meeting recording started: %s (%s)", state.title, state.meeting_id)
        return state

    def stop(self, timeout: float = 30.0) -> MeetingState | None:
        """Stop recording and return the finished meeting."""
        if not self.is_recording:
            return self._state
        self._stop.set()
        if self._thread:
            # The final segment still has to go through Whisper, which can take
            # a few seconds — wait for it rather than losing the last words.
            self._thread.join(timeout=timeout)
        with self._lock:
            if self._state:
                self._state.ended_at = datetime.now()
            state = self._state
        log.info("Meeting recording stopped: %s segments",
                 len(state.segments) if state else 0)
        return state

    # ── recording thread ──────────────────────────────────────────────────
    def _loop(self) -> None:
        # Imported here so the module stays importable without audio hardware
        # (tests, headless CI).
        import numpy as np
        from backend.modules.voice.audio_capture import AudioCapture

        cap = AudioCapture()
        try:
            cap.start()
        except Exception as e:
            log.error("Meeting recorder could not open the microphone: %s", e)
            with self._lock:
                self._error = f"microphone unavailable: {e}"
            return

        buf: list = []
        samples_per_segment = SAMPLE_RATE * SEGMENT_SECONDS
        buffered = 0
        try:
            while not self._stop.is_set():
                chunk = cap.get_chunk(timeout=0.5)
                if chunk is None:
                    continue
                buf.append(chunk)
                buffered += len(chunk)
                if buffered >= samples_per_segment:
                    self._flush(np.concatenate(buf))
                    buf, buffered = [], 0
            # Whatever is left when the user says "stop" is still part of the
            # meeting — transcribe it instead of dropping it.
            if buf:
                self._flush(np.concatenate(buf))
        except Exception as e:
            log.exception("Meeting recording loop failed: %s", e)
            with self._lock:
                self._error = str(e)
        finally:
            try:
                cap.stop()
            except Exception:
                pass

    def _flush(self, audio) -> None:
        """Transcribe one segment and append it to the transcript."""
        import numpy as np

        if audio is None or len(audio) < SAMPLE_RATE // 2:
            return
        # Skip near-silence so Whisper doesn't invent speech from room tone.
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))
        if rms < SILENCE_RMS:
            log.debug("Meeting segment skipped (silence, rms=%.1f)", rms)
            return

        try:
            from backend.modules.voice.pipeline import transcribe_array
            result = transcribe_array(audio)
        except Exception as e:
            log.warning("Meeting segment transcription failed: %s", e)
            return

        text = (result or {}).get("text", "").strip()
        if not text:
            return

        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "text": text,
            "language": (result or {}).get("language"),
        }
        with self._lock:
            if self._state is None:
                return
            self._state.segments.append(entry)
            path = self._state.path()
        # Persist immediately — a long meeting must survive a crash.
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning("Could not persist meeting segment: %s", e)
        log.info("Meeting segment: %s", text[:80])

    # ── recovery ──────────────────────────────────────────────────────────
    def last_meeting(self) -> MeetingState | None:
        """The in-memory meeting, or the most recent one from disk."""
        with self._lock:
            if self._state and self._state.segments:
                return self._state
        return load_latest()


def load_latest() -> MeetingState | None:
    """Rebuild the most recent meeting from its JSONL file."""
    if not MEETINGS_DIR.exists():
        return None
    files = sorted(MEETINGS_DIR.glob("*.jsonl"))
    if not files:
        return None
    return load(files[-1].stem)


def load(meeting_id: str) -> MeetingState | None:
    path = MEETINGS_DIR / f"{meeting_id}.jsonl"
    if not path.is_file():
        return None
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            segments.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    try:
        started = datetime.strptime(meeting_id, "%Y%m%d-%H%M%S")
    except ValueError:
        started = datetime.now()
    state = MeetingState(
        meeting_id=meeting_id,
        title=f"Meeting {started.strftime('%d.%m.%Y %H:%M')}",
        started_at=started,
        segments=segments,
    )
    if segments:
        try:
            state.ended_at = datetime.fromisoformat(segments[-1]["ts"])
        except Exception:
            pass
    return state


# Single shared recorder (one meeting at a time).
recorder = MeetingRecorder()
