"""A misplaced .env must announce itself, not vanish.

`load_dotenv()` returns quietly when the file is not there, so every setting
falls back to its default with no error anywhere. The symptom is a scatter of
apparently unrelated faults — wrong model, no voice, missing API key — for one
cause: the file is in the wrong folder.

It happens for a concrete reason. `git clone` into an existing directory
produces plasma\\plasma, the virtualenv gets made in the outer one, and .env is
naturally written next to .venv — one level above where Plasma reads it.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _probe(env_at: Path | None, tmp_path: Path) -> dict:
    """Import config with a fake project layout and report what it decided."""
    fake_root = tmp_path / "outer" / "plasma"
    (fake_root / "backend" / "core").mkdir(parents=True)
    # Copy the real config module into the fake tree so PROJECT_ROOT resolves
    # to fake_root exactly as it does in a real checkout.
    src = (ROOT / "backend" / "core" / "config.py").read_text(encoding="utf-8")
    (fake_root / "backend" / "core" / "config.py").write_text(src, encoding="utf-8")
    for pkg in (fake_root / "backend", fake_root / "backend" / "core"):
        (pkg / "__init__.py").write_text("", encoding="utf-8")

    if env_at is not None:
        env_at.parent.mkdir(parents=True, exist_ok=True)
        env_at.write_text("OLLAMA_MODEL=from-the-env-file\n", encoding="utf-8")

    script = tmp_path / "probe.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        from backend.core import config as c
        print(json.dumps({
            "loaded": c.ENV_LOADED,
            "hint": c.ENV_HINT,
            "model": c.config.OLLAMA_MODEL,
        }))
    """), encoding="utf-8")

    import json
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(fake_root)
    env.pop("OLLAMA_MODEL", None)      # must come from the file, not the shell
    proc = subprocess.run([sys.executable, str(script)], cwd=str(fake_root),
                          capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_env_in_the_project_root_is_loaded(tmp_path):
    root = tmp_path / "outer" / "plasma"
    result = _probe(root / ".env", tmp_path)
    assert result["loaded"] is True
    assert result["model"] == "from-the-env-file"
    assert result["hint"] == ""


def test_env_one_level_up_is_reported_not_silently_used(tmp_path):
    """The exact trap: .env beside .venv in the outer folder."""
    result = _probe(tmp_path / "outer" / ".env", tmp_path)
    assert result["loaded"] is False
    # Not loaded — reading config from outside the project would be worse than
    # saying what is wrong.
    assert result["model"] != "from-the-env-file"
    assert "WRONG" in result["hint"].upper() or "but there is one at" in result["hint"]
    assert "Move it" in result["hint"]


def test_no_env_anywhere_says_what_to_do(tmp_path):
    result = _probe(None, tmp_path)
    assert result["loaded"] is False
    assert "using its default" in result["hint"]
    assert ".env.example" in result["hint"]


def test_startup_announces_the_settings_file():
    """Silence here is what made this cost two rounds of debugging."""
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "Settings loaded from %s" in main
    assert "ENV_HINT" in main


def test_doctor_catches_the_misplaced_file():
    doctor = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
    assert "WRONG FOLDER" in doctor
    assert "ROOT.parent" in doctor
