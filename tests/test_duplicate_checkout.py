"""Two copies of Plasma on one machine must announce themselves.

`git clone <url> plasma` inside an existing `plasma` folder produces
plasma\\plasma — two complete checkouts. Both launch, both serve port 8000,
and nothing distinguishes them at the prompt. So .env gets edited in one,
`git pull` lands in one, and `python run_plasma.py` starts the other.

The symptoms have nothing to do with the real cause: settings that "don't
apply", a fix that "didn't work", a file that is not where you just put it.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _make_nested(tmp_path: Path) -> Path:
    """outer/plasma containing outer/plasma/plasma, both launchable."""
    outer = tmp_path / "plasma"
    inner = outer / "plasma"
    inner.mkdir(parents=True)
    launcher = (ROOT / "run_plasma.py").read_text(encoding="utf-8")
    (outer / "run_plasma.py").write_text(launcher, encoding="utf-8")
    (inner / "run_plasma.py").write_text(launcher, encoding="utf-8")
    return outer


def test_the_launcher_warns_from_the_outer_copy(tmp_path):
    outer = _make_nested(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(outer / "run_plasma.py")],
        cwd=str(outer), capture_output=True, text=True, timeout=90,
    )
    out = proc.stdout
    assert "ANOTHER PLASMA INSIDE THIS ONE" in out
    assert str(outer / "plasma") in out
    assert "cd " in out              # tells you where to go, not just that it is wrong


def test_the_inner_copy_says_nothing(tmp_path):
    """A correct checkout must not be nagged."""
    outer = _make_nested(tmp_path)
    inner = outer / "plasma"
    proc = subprocess.run(
        [sys.executable, str(inner / "run_plasma.py")],
        cwd=str(inner), capture_output=True, text=True, timeout=90,
    )
    assert "ANOTHER PLASMA" not in proc.stdout


def test_a_normal_checkout_says_nothing(tmp_path):
    solo = tmp_path / "plasma"
    solo.mkdir()
    (solo / "run_plasma.py").write_text(
        (ROOT / "run_plasma.py").read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(solo / "run_plasma.py")],
        cwd=str(solo), capture_output=True, text=True, timeout=90,
    )
    assert "ANOTHER PLASMA" not in proc.stdout


def test_doctor_reports_it_as_blocking():
    """It is not a nicety — every other reading from the wrong copy is a lie."""
    doctor = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
    assert "duplicate checkout" in doctor
    assert "ROOT / ROOT.name" in doctor
