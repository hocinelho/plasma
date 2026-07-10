"""Skill: update_check — check for Plasma updates on GitHub (PA-81).

Compares the local VERSION file against the latest GitHub release tag.
"""
from __future__ import annotations
import logging
from pathlib import Path

log = logging.getLogger("plasma.skill.update_check")

META = {
    "name": "update_check",
    "description": "Checks for newer Plasma versions on GitHub.",
    "triggers": [
        "check for updates",
        "is there an update",
        "any updates",
        "plasma version",
        "what version",
        "nach updates suchen",
        "gibt es ein update",
        "welche version",
    ],
    "example_utterances": [
        "Check for updates",
        "What version of Plasma am I running?",
        "Is there an update?",
        "Nach Updates suchen",
    ],
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = PROJECT_ROOT / "VERSION"
GITHUB_RELEASES_URL = "https://api.github.com/repos/hocinelho/plasma/releases/latest"


def _read_local_version() -> str:
    """Read the local version from the VERSION file."""
    try:
        return VERSION_FILE.read_text().strip()
    except Exception:
        return "unknown"


def _fetch_latest_version() -> str | None:
    """Fetch the latest release tag from GitHub. Returns None on failure."""
    try:
        from backend.core.http_client import get as http_get
        resp = http_get(GITHUB_RELEASES_URL, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        # Strip leading 'v' if present (e.g. "v0.12.0" -> "0.12.0")
        return tag.lstrip("v") if tag else None
    except Exception as e:
        log.warning(f"GitHub release check failed: {e}")
        return None


def _compare_versions(local: str, remote: str) -> int:
    """Compare semver strings. Returns -1 if local < remote, 0 if equal, 1 if local > remote."""
    try:
        local_parts = [int(x) for x in local.split(".")]
        remote_parts = [int(x) for x in remote.split(".")]
        max_len = max(len(local_parts), len(remote_parts))
        local_parts.extend([0] * (max_len - len(local_parts)))
        remote_parts.extend([0] * (max_len - len(remote_parts)))
        for lp, rp in zip(local_parts, remote_parts):
            if lp < rp:
                return -1
            if lp > rp:
                return 1
        return 0
    except (ValueError, AttributeError):
        if local < remote:
            return -1
        if local > remote:
            return 1
        return 0


def get_version_info() -> dict:
    """Return version info dict (used by both the skill and the API endpoint)."""
    local = _read_local_version()
    remote = _fetch_latest_version()

    result = {
        "version": local,
        "latest": remote,
        "update_available": False,
    }

    if remote and local != "unknown":
        result["update_available"] = _compare_versions(local, remote) < 0

    return result


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").lower().strip()
    local = _read_local_version()

    # Just asking for current version
    if any(p in utterance for p in ["plasma version", "what version", "welche version"]):
        if local == "unknown":
            return "I couldn't determine the current Plasma version — the VERSION file is missing."
        return f"You're running Plasma v{local}."

    # Check for updates
    if local == "unknown":
        return "I couldn't determine the current version — the VERSION file is missing."

    remote = _fetch_latest_version()
    if remote is None:
        return "Couldn't check for updates — no internet connection or GitHub is unreachable."

    cmp = _compare_versions(local, remote)
    if cmp < 0:
        return f"Update available: v{remote} (you're on v{local}). Visit the GitHub releases page to download."
    elif cmp == 0:
        return f"You're up to date (v{local})."
    else:
        return f"You're running a newer version (v{local}) than the latest release (v{remote})."


def self_test() -> bool:
    return isinstance(META.get("triggers"), list) and callable(run)
