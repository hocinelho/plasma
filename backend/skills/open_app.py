"""Opens common Windows apps via PowerShell."""
import subprocess
import re

APPS = {
    "notepad":    "notepad.exe",
    "calculator": "calc.exe",
    "calendar":   "outlookcal:",
    "outlook":    "outlook.exe",
    "chrome":     "chrome.exe",
    "edge":       "msedge.exe",
    "explorer":   "explorer.exe",
    "terminal":   "wt.exe",
    "pycharm":    "pycharm",
    "spotify":    "spotify:",
}

META = {
    "name": "open_app",
    "description": "Opens a Windows application by name.",
    "triggers": ["open ", "launch ", "start "],
}

def run(args=None):
    utterance = (args or {}).get("utterance", "").lower()
    m = re.search(r"(?:open|launch|start)\s+([a-z ]+?)(?:\s+for\s+me|\s+please|$)", utterance)
    if not m:
        return "Sorry, I didn't catch which app to open."
    name = m.group(1).strip()
    cmd = APPS.get(name)
    if not cmd:
        return f"I don't know how to open {name}. Known apps: {', '.join(APPS)}."
    try:
        subprocess.Popen(cmd, shell=True)
        return f"Opening {name}."
    except Exception as e:
        return f"Could not open {name}: {e}"

def self_test():
    # Don't actually launch anything — just verify the dict lookup works.
    return "notepad.exe" == APPS["notepad"]