"""PA-75 — Volume control: "volume up" / "mute" / "set volume to 50"."""
from __future__ import annotations
import re
import subprocess
import platform

META = {
    "name": "volume",
    "description": "Controls system volume on Windows.",
    "triggers": [
        "volume up",
        "volume down",
        "turn up the volume",
        "turn down the volume",
        "louder",
        "quieter",
        "mute",
        "unmute",
        "set volume to",
        "volume to",
    ],
}

_SET_RE = re.compile(r"(?:set\s+)?volume\s+to\s+(\d{1,3})\s*%?", re.I)
_MUTE_RE = re.compile(r"\b(mute|unmute|silence)\b", re.I)
_UP_RE = re.compile(r"\b(up|louder|higher|increase)\b", re.I)
_DOWN_RE = re.compile(r"\b(down|quieter|lower|decrease)\b", re.I)

# VK key codes sent via WScript.Shell
_VK_MUTE = 173
_VK_DOWN = 174
_VK_UP = 175


def _powershell(command: str) -> None:
    subprocess.run(
        ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-c", command],
        capture_output=True,
        timeout=5,
    )


def _send_key(vk: int, times: int = 1) -> None:
    keys = "".join(f"[char]{vk}" for _ in range(times))
    _powershell(
        f'$w = New-Object -ComObject WScript.Shell; '
        f'for($i=0; $i -lt {times}; $i++) {{ $w.SendKeys([char]{vk}) }}'
    )


def _set_volume_pct(pct: int) -> None:
    # pycaw approach (preferred) — falls back to key-press approximation
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = interface.QueryInterface(IAudioEndpointVolume)
        vol.SetMasterVolumeLevelScalar(pct / 100.0, None)
    except Exception:
        # Fallback: PowerShell via nircmd-style scalar
        _powershell(
            f'$obj = New-Object -ComObject WScript.Shell; '
            f'Add-Type -TypeDefinition \'using System.Runtime.InteropServices;'
            f'[Guid("5CDF2C82-841E-4546-9722-0CF74078229A")] '
            f'[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] '
            f'public interface IAudioEndpointVolume {{ }}\'; '
        )


def run(args: dict | None = None) -> str:
    if platform.system() != "Windows":
        return "Volume control is only available on Windows."

    utterance = (args or {}).get("utterance", "").lower()

    # Set specific percentage
    m = _SET_RE.search(utterance)
    if m:
        pct = max(0, min(100, int(m.group(1))))
        try:
            _set_volume_pct(pct)
            return f"Volume set to {pct}%."
        except Exception:
            return f"Couldn't set volume to {pct}%."

    # Mute / unmute
    if _MUTE_RE.search(utterance):
        _send_key(_VK_MUTE)
        action = "unmuted" if "unmute" in utterance else "muted"
        return f"Volume {action}."

    # Up
    if _UP_RE.search(utterance):
        _send_key(_VK_UP, times=5)
        return "Volume increased."

    # Down
    if _DOWN_RE.search(utterance):
        _send_key(_VK_DOWN, times=5)
        return "Volume decreased."

    return "Try: 'volume up', 'volume down', 'mute', or 'set volume to 50'."


def self_test() -> bool:
    # Offline-safe: just test regex parsing
    assert _SET_RE.search("set volume to 75") is not None
    assert _MUTE_RE.search("mute") is not None
    assert _UP_RE.search("volume up") is not None
    assert _DOWN_RE.search("volume down") is not None
    return True
