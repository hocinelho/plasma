"""Startup model check — warn when a configured Ollama model isn't installed."""
from unittest.mock import patch

from backend.modules.router import ollama_client as oc


def test_model_installed_matches_latest_suffix():
    installed = ["mistral:latest", "llama3.2-vision:latest"]
    assert oc._model_installed("mistral:latest", installed)
    assert oc._model_installed("mistral", installed)          # bare name matches
    assert oc._model_installed("llama3.2-vision:latest", installed)
    assert not oc._model_installed("llama3.2:3b", installed)  # not pulled


def test_check_warns_for_missing_model():
    installed = ["mistral:latest", "moondream:latest"]
    cfg = type("C", (), {
        "OLLAMA_MODEL": "llama3.2:3b",                 # not installed → warn
        "LOCATE_VISION_OLLAMA_MODEL": "moondream",     # installed → ok
    })
    with patch.object(oc, "list_installed_models", return_value=installed), \
         patch.object(oc, "config", cfg):
        warnings = oc.check_configured_models()
    assert len(warnings) == 1
    assert "ollama pull llama3.2:3b" in warnings[0]


def test_check_silent_when_all_present():
    installed = ["mistral:latest", "llama3.2-vision:latest"]
    cfg = type("C", (), {
        "OLLAMA_MODEL": "mistral:latest",
        "LOCATE_VISION_OLLAMA_MODEL": "llama3.2-vision:latest",
    })
    with patch.object(oc, "list_installed_models", return_value=installed), \
         patch.object(oc, "config", cfg):
        assert oc.check_configured_models() == []


def test_check_silent_when_ollama_unreachable():
    cfg = type("C", (), {"OLLAMA_MODEL": "whatever", "LOCATE_VISION_OLLAMA_MODEL": "x"})
    with patch.object(oc, "list_installed_models", return_value=[]), \
         patch.object(oc, "config", cfg):
        assert oc.check_configured_models() == []
