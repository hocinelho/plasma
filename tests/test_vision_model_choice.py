"""Describe the world with the best model on the disk, not the first one pulled.

Hocine's .env said LOCATE_VISION_OLLAMA_MODEL=moondream — 1.8B, the weakest
vision model he had — while llama3.2-vision (11B) sat installed and unused on
the same machine. Recognition was "not accurate, doesn't know many things",
and the cause was a configuration line, not the code.

Worse, availability was gated on that line existing at all: a machine with a
vision model pulled and ready reported "no vision model" and fell back to the
80-class detector.
"""
from unittest.mock import patch

import pytest

from backend.core.config import config
from backend.skills import locate


@pytest.fixture
def no_config(monkeypatch):
    monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_MODEL", "")
    monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_FALLBACKS", "")


def _installed(names):
    return patch("backend.modules.router.ollama_client.list_installed_models",
                 return_value=names)


class TestRanking:
    def test_ranked_by_description_quality_not_size(self):
        """Qwen2.5-VL beats a larger LLaVA for scene description."""
        assert locate._rank_vision_model("qwen2.5vl:7b") < \
            locate._rank_vision_model("llava:34b")

    def test_moondream_is_last_among_known_models(self):
        known = ["qwen2.5vl:7b", "minicpm-v:latest", "llama3.2-vision:latest",
                 "llava:latest", "moondream:latest"]
        assert max(known, key=locate._rank_vision_model) == "moondream:latest"

    def test_a_text_only_model_is_never_preferred(self):
        assert locate._rank_vision_model("qwen3:8b") > \
            locate._rank_vision_model("moondream:latest")


class TestAutoSelection:
    def test_picks_the_strongest_installed(self, no_config):
        with _installed(["moondream:latest", "llama3.2-vision:latest",
                         "llava:latest", "qwen3:8b"]):
            assert locate.best_installed_vision_model() == "llama3.2-vision:latest"

    def test_prefers_qwen_vl_when_present(self, no_config):
        with _installed(["llama3.2-vision:latest", "qwen2.5vl:7b"]):
            assert locate.best_installed_vision_model() == "qwen2.5vl:7b"

    def test_none_when_no_vision_model_is_installed(self, no_config):
        with _installed(["qwen3:8b", "mistral:latest"]):
            assert locate.best_installed_vision_model() is None

    def test_none_when_ollama_is_unreachable(self, no_config):
        with patch("backend.modules.router.ollama_client.list_installed_models",
                   side_effect=OSError("connection refused")):
            assert locate.best_installed_vision_model() is None


class TestConfigStillWins:
    def test_an_explicit_choice_is_honoured(self, monkeypatch):
        monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_MODEL", "moondream")
        monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_FALLBACKS", "")
        with _installed(["qwen2.5vl:7b", "moondream:latest"]):
            assert locate._ollama_vision_models()[0] == "moondream"

    def test_fallbacks_are_kept_in_order(self, monkeypatch):
        monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_MODEL", "qwen2.5vl")
        monkeypatch.setattr(config, "LOCATE_VISION_OLLAMA_FALLBACKS", "llava,moondream")
        assert locate._ollama_vision_models() == ["qwen2.5vl", "llava", "moondream"]


class TestAvailability:
    def test_available_when_a_model_is_merely_installed(self, no_config):
        """The old gate needed a .env line; a pulled model was ignored."""
        with _installed(["llama3.2-vision:latest"]):
            assert locate._ollama_vision_available() is True

    def test_unavailable_with_no_vision_model_anywhere(self, no_config):
        with _installed(["qwen3:8b"]):
            assert locate._ollama_vision_available() is False
