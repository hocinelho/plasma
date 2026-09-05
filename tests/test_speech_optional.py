"""Speech recognition must be optional, not load-bearing.

faster-whisper pulls in ctranslate2, which pulls in PyTorch, which loads
native DLLs. Any of those can fail for reasons unrelated to Plasma — most
sharply on a managed work laptop, where Windows application-control policy
refuses to load an unsigned .dll out of a user directory and raises
WinError 4551.

Imported at module scope, that took the whole backend down: no avatar, no
chat, no wallpaper, because the microphone could not start. These tests hold
the boundary that keeps one blocked DLL from costing everything else.
"""
import builtins

import pytest

from backend.modules.voice import asr

WINDOWS_POLICY_ERROR = (
    "[WinError 4551] Eine Anwendungssteuerungsrichtlinie hat diese Datei "
    'blockiert. Error loading "torch\\lib\\shm.dll" or one of its dependencies.'
)


@pytest.fixture
def blocked_import(monkeypatch):
    """Make `import faster_whisper` fail the way the work laptop does."""
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "faster_whisper" or name.startswith("faster_whisper."):
            raise OSError(WINDOWS_POLICY_ERROR)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_the_whole_app_still_boots_when_whisper_is_blocked(tmp_path):
    """The regression this exists for: the backend would not start at all.

    Run in a subprocess with the import blocked at the meta-path level, which
    is as close to the real machine as this can get. Deliberately NOT
    importlib.reload() in-process: reloading rebinds SpeechUnavailable to a
    fresh class object while other modules keep the old one, so `except
    SpeechUnavailable` silently stops matching and later tests fail for
    reasons that have nothing to do with them.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(asr.__file__).parents[3]
    script = tmp_path / "boot.py"
    script.write_text(
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] == 'faster_whisper':\n"
        "            raise OSError('[WinError 4551] blocked by policy')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import backend.main\n"
        "assert backend.main.app is not None\n"
        "from backend.modules.voice.asr import available\n"
        "ok, why = available()\n"
        "assert ok is False, 'speech should report unavailable'\n"
        "print('BOOTED')\n",
        encoding="utf-8",
    )
    import os
    env = dict(os.environ)
    # Python puts the *script's* directory on sys.path, not the cwd, and the
    # script lives in tmp_path — so point PYTHONPATH at the repo explicitly.
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root), capture_output=True, text=True, timeout=180, env=env,
    )
    assert "BOOTED" in proc.stdout, (
        f"the backend failed to start without speech recognition:\n"
        f"{proc.stderr[-2000:]}"
    )


def test_available_reports_the_policy_block_in_plain_words(blocked_import):
    ok, why = asr.available()
    assert ok is False
    assert "application control policy" in why
    assert "IT restriction" in why
    assert "Everything else works" in why
    # The raw DLL path and error number help nobody standing at the keyboard.
    assert "shm.dll" not in why


def test_a_missing_package_says_how_to_install_it(monkeypatch):
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name.startswith("faster_whisper"):
            raise ModuleNotFoundError("No module named 'faster_whisper'",
                                      name="faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)
    ok, why = asr.available()
    assert ok is False
    assert "pip install -r requirements.txt" in why


def test_constructing_the_asr_raises_something_readable(blocked_import):
    with pytest.raises(asr.SpeechUnavailable) as e:
        asr.WhisperASR()
    assert "application control policy" in str(e.value)


def test_transcription_returns_the_reason_rather_than_raising(blocked_import, monkeypatch):
    """The request handler must get a message it can show, not a traceback."""
    np = pytest.importorskip("numpy")
    from backend.modules.voice import pipeline

    # get_asr() memoises. An earlier test in the same run may have left an ASR
    # cached, which would skip the very path under test — so clear it, via
    # monkeypatch so the next test inherits nothing from this one.
    monkeypatch.setattr(pipeline, "_asr", None)

    result = pipeline.transcribe_array(np.zeros(32000, dtype=np.int16))
    assert result["text"] == ""
    assert "application control policy" in result["error"]


def test_whisper_is_not_imported_at_module_scope():
    """A top-level import is exactly the regression this guards against."""
    src = open(asr.__file__, encoding="utf-8").read()
    head = src.split("class WhisperASR")[0]
    assert "\nfrom faster_whisper import" not in head
    assert "\nimport faster_whisper" not in head


def test_health_reports_speech_separately():
    main = open(
        __import__("pathlib").Path(asr.__file__).parents[3] / "backend" / "main.py",
        encoding="utf-8",
    ).read()
    assert '"asr": "ok" if speech_ok else "unavailable"' in main


def test_doctor_forces_a_real_import():
    """find_spec() only proves the package is on disk — a blocked DLL still
    passes it, and the user finds out when they first try to speak."""
    doctor = open(
        __import__("pathlib").Path(asr.__file__).parents[3] / "scripts" / "doctor.py",
        encoding="utf-8",
    ).read()
    assert "def check_speech()" in doctor
    assert "import faster_whisper" in doctor
    assert "4551" in doctor
