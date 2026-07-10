"""
PA-30 — Audit log for outbound cloud LLM calls.

Every cloud call appends one JSON line to `.plasma/audit.log`. This gives the
user a permanent record of what was sent to a third-party API (model name,
provider, sizes, latency, success/failure) without storing the message bodies
themselves — PII has already been stripped upstream by pii_redactor.

Format: one JSON object per line (JSONL), so the file is grep-friendly and
easy to ingest with `jq`. Schema:

    {
      "ts": "2026-05-13T14:32:01.123Z",
      "provider": "generativelanguage.googleapis.com",
      "model": "gemini-2.0-flash",
      "mode": "stream" | "full",
      "msg_count": 4,
      "prompt_chars": 612,
      "response_chars": 48,
      "latency_ms": 873,
      "status": "ok" | "error",
      "error": "..."   # only present when status=="error"
    }
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from backend.core.config import config

log = logging.getLogger("plasma.audit_log")

_AUDIT_PATH = config.PLASMA_DIR / "audit.log"


def _provider_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or "unknown"
        return host
    except Exception:
        return "unknown"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_call(
    *,
    base_url: str,
    model: str,
    mode: str,
    messages: list[dict],
    response_text: str,
    latency_ms: int,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """Append one entry to .plasma/audit.log. Never raises."""
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        entry = {
            "ts": _iso_now(),
            "provider": _provider_from_url(base_url),
            "model": model,
            "mode": mode,
            "msg_count": len(messages),
            "prompt_chars": prompt_chars,
            "response_chars": len(response_text or ""),
            "latency_ms": latency_ms,
            "status": status,
        }
        if error:
            entry["error"] = error
        with _AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"audit log write failed: {e}")


def read_entries(limit: int | None = None) -> list[dict]:
    """Read entries back from the audit log (newest last). Used by tests / UI."""
    if not _AUDIT_PATH.exists():
        return []
    lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[-limit:]
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
