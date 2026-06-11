"""Tests for PA-46 — Windows installer / launcher infrastructure."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── run_plasma.py module ──────────────────────────────────────────────────

def test_run_plasma_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "run_plasma.py").exists()


def test_run_plasma_find_project_root():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import run_plasma
    importlib.reload(run_plasma)
    found = run_plasma._find_project_root()
    assert found == root


def test_run_plasma_find_root_frozen(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import run_plasma
    importlib.reload(run_plasma)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/fake/bundle", raising=False)
    found = run_plasma._find_project_root()
    assert found == Path("/fake/bundle")


# ── plasma.spec ───────────────────────────────────────────────────────────

def test_spec_file_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "plasma.spec").exists()


def test_spec_references_run_plasma():
    root = Path(__file__).resolve().parents[1]
    text = (root / "plasma.spec").read_text()
    assert "run_plasma.py" in text


def test_spec_bundles_frontend():
    root = Path(__file__).resolve().parents[1]
    text = (root / "plasma.spec").read_text()
    assert "frontend" in text


def test_spec_bundles_version():
    root = Path(__file__).resolve().parents[1]
    text = (root / "plasma.spec").read_text()
    assert "VERSION" in text


def test_spec_has_hidden_imports():
    root = Path(__file__).resolve().parents[1]
    text = (root / "plasma.spec").read_text()
    for mod in ["uvicorn", "backend.core.config", "sounddevice", "numpy"]:
        assert mod in text, f"missing hiddenimport: {mod}"


# ── build_installer.py ───────────────────────────────────────────────────

def test_build_script_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts" / "build_installer.py").exists()


def test_build_script_importable():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import build_installer
    importlib.reload(build_installer)
    assert hasattr(build_installer, "main")


# ── .gitignore entries ────────────────────────────────────────────────────

def test_gitignore_excludes_build_artifacts():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".gitignore").read_text()
    assert "build/" in text
    assert "dist/" in text
