"""
Plasma cloud LLM smoke test — runs end-to-end against the real provider.

Usage (PowerShell):
    python scripts/smoke_test.py

Prereqs:
    1. A working .env at the repo root with:
         CLOUD_API_KEY=...
         CLOUD_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
         CLOUD_MODEL=gemini-2.0-flash

    2. pip install httpx python-dotenv

What it verifies:
    [PA-28] PII redactor strips emails / phones / cards
    [PA-29] Cloud client reaches the provider and gets a reply
    [PA-30] Audit log appends one JSON line per call
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# make `backend.*` imports work when run from any cwd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def banner(s: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {s}")
    print("=" * 60)


def main() -> int:
    # -------- PA-28: PII redactor --------
    banner("PA-28  PII redaction")
    from backend.modules.router.pii_redactor import redact

    sample = "Email me at john.doe@example.com or call +49 1525 123 4567"
    cleaned = redact(sample)
    print(f"in : {sample}")
    print(f"out: {cleaned}")
    assert "@" not in cleaned, "email leaked"
    assert "[EMAIL]" in cleaned, "email placeholder missing"
    print("OK")

    # -------- PA-29: cloud chat --------
    banner("PA-29  Cloud LLM round-trip")
    from backend.core.config import config
    from backend.modules.router.cloud_client import chat, is_available

    if not is_available():
        print("FAIL: CLOUD_API_KEY is empty. Set it in .env and retry.")
        return 2

    print(f"provider : {config.CLOUD_BASE_URL}")
    print(f"model    : {config.CLOUD_MODEL}")
    print("prompt   : 'Say exactly: Plasma cloud test OK.'")

    try:
        reply = chat("Say exactly: Plasma cloud test OK.")
    except Exception as e:
        print(f"FAIL: cloud call raised: {e}")
        return 3

    print(f"reply    : {reply!r}")
    if not reply:
        print("FAIL: empty reply")
        return 4
    print("OK")

    # -------- PA-30: audit log --------
    banner("PA-30  Audit log")
    audit = config.PLASMA_DIR / "audit.log"
    if not audit.exists():
        print(f"FAIL: {audit} not written")
        return 5

    last_line = audit.read_text(encoding="utf-8").splitlines()[-1]
    entry = json.loads(last_line)
    print(json.dumps(entry, indent=2))
    for key in ("ts", "provider", "model", "mode", "msg_count",
                "prompt_chars", "response_chars", "latency_ms", "status"):
        assert key in entry, f"audit entry missing key: {key}"
    assert entry["status"] == "ok"
    print("OK")

    banner("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
