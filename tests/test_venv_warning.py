"""run_plasma.py must say when it is running from the wrong Python.

The failure this catches is invisible from the outside. Plasma starts, logs
"Application startup complete", and then has no microphone, no voice and no
clap-to-wake — because sounddevice, faster-whisper and piper live in .venv
while the interpreter actually running is the system or conda one. Every
symptom points at a broken feature; none of them point at the interpreter.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "run_plasma.py").read_text(encoding="utf-8")


def _run_launcher_in(project: Path) -> str:
    """Start the launcher in a fake project and return what it printed.

    It will fail on `import uvicorn` almost immediately in the environments
    that matter here — the warning is printed well before that, which is the
    whole point.
    """
    (project / "run_plasma.py").write_text(LAUNCHER, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(project / "run_plasma.py")],
        cwd=str(project), capture_output=True, text=True, timeout=120,
    )
    return proc.stdout


def test_warns_when_a_venv_exists_but_is_not_active(tmp_path):
    project = tmp_path / "plasma"
    (project / ".venv" / "bin").mkdir(parents=True)
    out = _run_launcher_in(project)
    assert "THE VIRTUAL ENVIRONMENT IS NOT ACTIVE" in out
    assert "sounddevice" in out          # names what is actually missing


def test_it_finds_a_venv_one_level_up(tmp_path):
    """The real layout: .venv sits beside the repo, not inside it —
    PycharmProjects/plasma/.venv with the code in plasma/plasma."""
    project = tmp_path / "plasma" / "plasma"
    project.mkdir(parents=True)
    (tmp_path / "plasma" / ".venv" / "bin").mkdir(parents=True)
    out = _run_launcher_in(project)
    assert "THE VIRTUAL ENVIRONMENT IS NOT ACTIVE" in out


def test_silent_when_there_is_no_venv_to_activate(tmp_path):
    """Someone installing straight into their system Python is not confused,
    they are just doing that — do not nag them."""
    project = tmp_path / "plasma"
    project.mkdir()
    assert "VIRTUAL ENVIRONMENT IS NOT ACTIVE" not in _run_launcher_in(project)


def test_it_explains_the_consequence_not_just_the_fact(tmp_path):
    """"Venv not active" means nothing to most people; "no microphone, no
    voice, no clap" is the thing they are actually experiencing."""
    project = tmp_path / "plasma"
    (project / ".venv" / "bin").mkdir(parents=True)
    out = _run_launcher_in(project)
    assert "microphone" in out and "clap" in out


def test_it_is_a_warning_not_a_refusal():
    """Everything that IS installed still works — refusing to start would be
    worse than starting degraded."""
    block = LAUNCHER.split("def _warn_if_the_venv_is_not_active", 1)[1].split("def main", 1)[0]
    assert "sys.exit" not in block and "SystemExit" not in block
