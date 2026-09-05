"""Turn a raw meeting transcript into structured minutes.

The transcript comes from Whisper, so it is unpunctuated, has no speaker
labels and contains mis-hearings. The prompt is written accordingly: the model
is told to work only from what is there and to leave a section empty rather
than inventing decisions nobody made.
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("plasma.meeting")

# Long meetings can exceed the local model's context. Keep the head and the
# tail — openings and closings carry the agenda and the decisions.
MAX_CHARS = 12_000

_PROMPT_EN = """You are writing the minutes of a meeting.

Below is an automatic transcript. It has no speaker labels, no punctuation in
places, and may contain transcription errors — interpret it sensibly.

Return ONLY a JSON object, no other text, with exactly these keys:
  "summary":   2-4 sentences on what the meeting was about.
  "key_points": array of the main points discussed (short strings).
  "decisions":  array of decisions actually made.
  "actions":    array of {"task": "...", "owner": "..."} — owner "" if unclear.
  "open_questions": array of unresolved questions.

Rules:
- Use ONLY what is in the transcript. Invent nothing.
- If a section has nothing in it, return an empty array. Do not pad it.
- Write in the same language as the transcript.

TRANSCRIPT:
"""


def _trim(transcript: str) -> str:
    if len(transcript) <= MAX_CHARS:
        return transcript
    head = transcript[: MAX_CHARS // 2]
    tail = transcript[-MAX_CHARS // 2:]
    return f"{head}\n\n[... middle of the meeting omitted ...]\n\n{tail}"


def _extract_json(raw: str) -> dict | None:
    """Pull a JSON object out of an LLM reply that may be wrapped in prose."""
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = raw[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v not in ("", None)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _fallback(transcript: str) -> dict:
    """Used when the model is unavailable or returns unusable output.

    Never pretend to have understood the meeting — hand back the transcript
    with an explicit note so the Word document is still worth having.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript) if s.strip()]
    return {
        "summary": "Automatic summary unavailable — the full transcript is included below.",
        "key_points": sentences[:10],
        "decisions": [],
        "actions": [],
        "open_questions": [],
        "degraded": True,
    }


def summarize(transcript: str) -> dict:
    """Summarize a transcript into minutes. Always returns a usable dict."""
    transcript = (transcript or "").strip()
    if not transcript:
        return {
            "summary": "No speech was captured in this meeting.",
            "key_points": [], "decisions": [], "actions": [],
            "open_questions": [], "degraded": True,
        }

    try:
        from backend.modules.router.chat_service import _llm_reply
        raw = _llm_reply(
            user_message=_PROMPT_EN + _trim(transcript),
            history=[],
            system_prompt=(
                "You write concise, accurate meeting minutes. You reply with "
                "JSON only — no preamble, no commentary, no code fences."
            ),
        )
    except Exception as e:
        log.warning("Meeting summarization failed: %s", e)
        return _fallback(transcript)

    parsed = _extract_json(raw)
    if not parsed:
        log.warning("Meeting summary was not valid JSON; falling back.")
        return _fallback(transcript)

    actions = []
    for a in _as_list(parsed.get("actions")):
        if isinstance(a, dict):
            task = str(a.get("task", "")).strip()
            if task:
                actions.append({"task": task, "owner": str(a.get("owner", "")).strip()})
        elif isinstance(a, str):
            actions.append({"task": a.strip(), "owner": ""})

    return {
        "summary": str(parsed.get("summary", "")).strip(),
        "key_points": [str(x).strip() for x in _as_list(parsed.get("key_points"))],
        "decisions": [str(x).strip() for x in _as_list(parsed.get("decisions"))],
        "actions": actions,
        "open_questions": [str(x).strip() for x in _as_list(parsed.get("open_questions"))],
        "degraded": False,
    }
