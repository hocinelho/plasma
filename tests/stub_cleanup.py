"""Shared helper to undo sys.modules stubbing once a test file's tests finish.

Several sprint test files insert fake `backend.modules.voice.*` modules into
sys.modules at collection time so backend.main can be imported without native
deps (numpy/faster_whisper/resemblyzer) installed. Without cleanup those stubs
leak into other test files for the rest of the pytest session, since pytest
collects (imports) every test module before running any tests.
"""
import sys


def snapshot(names):
    """Capture whatever currently occupies each sys.modules[name]."""
    return {name: sys.modules.get(name) for name in names}


def restore(snapshot):
    """Put sys.modules back to what it was before stubbing, per snapshot()."""
    for name, original in snapshot.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
