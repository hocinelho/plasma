"""Skill: open_app — launches common Windows apps, websites, and system actions."""
from __future__ import annotations
import logging
import re
import subprocess

log = logging.getLogger("plasma.skill.open_app")

# Command types:
#   "shell"   -> subprocess.Popen(cmd, shell=True) — ordinary exe in PATH
#   "uri"     -> os.startfile(uri)                 — protocol handler (ms-settings:, etc.)
#   "start"   -> start "" "<name>"                 — looks up Start Menu / default handler
#   "url"     -> open a website in default browser
APPS: dict[str, tuple[str, str]] = {
    # System apps
    "notepad":    ("shell", "notepad.exe"),
    "calculator": ("shell", "calc.exe"),
    "calc":       ("shell", "calc.exe"),
    "explorer":   ("shell", "explorer.exe"),
    "files":      ("shell", "explorer.exe"),
    "terminal":   ("start", "wt"),
    "powershell": ("shell", "powershell.exe"),
    "settings":   ("uri",   "ms-settings:"),

    # Browsers / aliases — use `start` so Windows finds them via Start Menu
    "chrome":     ("start", "chrome"),
    "edge":       ("start", "msedge"),
    "firefox":    ("start", "firefox"),

    # Office / productivity
    "outlook":    ("start", "outlook"),
    "word":       ("start", "winword"),
    "excel":      ("start", "excel"),
    "pycharm":    ("start", "pycharm"),
    "spotify":    ("start", "spotify"),

    # Web shortcuts
    "google":     ("url",   "https://www.google.com"),
    "youtube":    ("url",   "https://www.youtube.com"),
    "github":     ("url",   "https://github.com"),
    "chatgpt":    ("url",   "https://chatgpt.com"),
    "claude":     ("url",   "https://claude.ai"),
}


META = {
    "name": "open_app",
    "description": "Opens a Windows application, system page, or website by name.",
    "triggers": [
        "open ",
        "launch ",
        "start ",
    ],
    "example_utterances": [
        "Open Notepad",
        "Launch Calculator",
        "Open Google",
        "Start Chrome",
    ],
}


def _launch(kind: str, target: str) -> None:
    import os
    if kind == "shell":
        subprocess.Popen(target, shell=True)
    elif kind == "uri":
        os.startfile(target)
    elif kind == "start":
        # Windows `start` in cmd: `start "" "<name>"` opens via Start Menu index
        subprocess.Popen(f'start "" {target}', shell=True)
    elif kind == "url":
        os.startfile(target)
    else:
        raise ValueError(f"Unknown app kind: {kind}")


def run(args: dict | None = None) -> str:
    utterance = ((args or {}).get("utterance") or "").lower().strip()

    # Pull the app name after "open"/"launch"/"start"
    m = re.search(
        r"(?:open|launch|start)\s+([a-z][a-z ]*?)(?:\s+(?:for me|please|now))?\s*[.!?]?\s*$",
        utterance,
    )
    if not m:
        return "Sorry, I didn't catch which app to open."

    name = m.group(1).strip()

    # Strip leading "a " / "the "
    name = re.sub(r"^(?:a|the)\s+", "", name)

    if name not in APPS:
        known = ", ".join(sorted(APPS.keys()))
        return f"I don't know how to open {name}. I know: {known}."

    kind, target = APPS[name]
    try:
        _launch(kind, target)
        log.info(f"Launched: {name} via {kind} -> {target}")
        friendly = {"shell": "Opening", "uri": "Opening", "start": "Opening", "url": "Loading"}
        return f"{friendly[kind]} {name}."
    except FileNotFoundError:
        return f"I couldn't find {name} on this machine."
    except Exception as e:
        log.warning(f"Failed to open {name}: {e}")
        return f"I couldn't open {name}."


def self_test() -> bool:
    # Don't actually launch anything during load; just verify lookup.
    return APPS.get("notepad") == ("shell", "notepad.exe") and "google" in APPS