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
# Words that follow "open"/"launch"/"start" in ordinary speech rather than
# naming a program. The triggers have to be this broad — "open " really is
# how people ask — so the way out is recognising when the object is not an
# application at all.
_NOT_AN_APP = frozenset({
    "over", "again", "now", "here", "there", "up", "out", "off", "on",
    "working", "talking", "listening", "recording", "moving", "walking",
    "it", "that", "this", "one", "them", "with", "from", "to", "for",
    "your", "my", "his", "her", "our", "their", "yourself", "myself",
    "the day", "a conversation", "the conversation", "a new one",
})

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
        return None                # not "open <something>" — let the LLM have it

    name = m.group(1).strip()

    # Strip leading "a " / "the "
    name = re.sub(r"^(?:a|the)\s+", "", name)

    # "start over", "start again", "open up to me" — the verb is there but the
    # word after it is not an application, it is the rest of an ordinary
    # sentence. Listing the apps she knows in reply to "start over" is the
    # kind of answer that makes her feel like a phrasebook.
    if name in _NOT_AN_APP:
        return None

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