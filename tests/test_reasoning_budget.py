"""A reasoning model must not spend the whole reply budget thinking.

The complaint was "he is not smart, can't answer why or what do you think" —
and the measurements said the same thing: replies of 31, 50 and 20 characters
in a real session.

The cause is arithmetic, not intelligence. qwen3 is a hybrid-reasoning model:
it writes a <think> block before the answer, and that block is spent from the
SAME num_predict allowance. At the shipped cap of 160 tokens the thinking used
it up, strip_reasoning removed the thinking, and what reached the user was the
stub of an answer that never got written. The questions that make a model
think longest — "why…", "what do you think…" — came back emptiest, which is
exactly backwards from what a person expects.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.config import config  # noqa: E402
from backend.modules.router import ollama_client as oc  # noqa: E402


class TestRecognisingAReasoningModel:
    def test_qwen3_is_one(self):
        assert oc.is_reasoning_model("qwen3:8b")
        assert oc.is_reasoning_model("qwen3:14b-instruct")

    def test_qwen25_is_not(self):
        """The version matters: qwen2.5 has no thinking mode, and sending it
        /no_think would just be a stray token in its prompt."""
        assert not oc.is_reasoning_model("qwen2.5:14b")

    def test_the_other_common_ones_are_recognised(self):
        for m in ("deepseek-r1:7b", "qwq:32b", "magistral:24b"):
            assert oc.is_reasoning_model(m), m

    def test_an_unknown_model_is_left_alone(self):
        assert not oc.is_reasoning_model("llama3.2:3b")
        assert not oc.is_reasoning_model("")


class TestTurningThinkingOff:
    def test_it_is_off_by_default_for_a_reasoning_model(self, monkeypatch):
        """For a voice assistant the deliberation is never shown and never
        spoken, so it buys nothing and costs both the budget and the wait."""
        monkeypatch.setattr(config, "OLLAMA_THINK", "")
        assert oc.thinking_disabled("qwen3:8b") is True

    def test_a_plain_model_is_untouched(self, monkeypatch):
        monkeypatch.setattr(config, "OLLAMA_THINK", "")
        assert oc.thinking_disabled("llama3.2:3b") is False

    def test_it_can_be_kept_on_deliberately(self, monkeypatch):
        """Worth it on a fast machine, where the quality is free."""
        monkeypatch.setattr(config, "OLLAMA_THINK", "true")
        assert oc.thinking_disabled("qwen3:8b") is False

    def test_it_can_be_forced_off_for_anything(self, monkeypatch):
        monkeypatch.setattr(config, "OLLAMA_THINK", "false")
        assert oc.thinking_disabled("llama3.2:3b") is True

    def test_it_reuses_the_existing_knob(self):
        """A second env var meaning nearly the same thing is how a config
        becomes unusable."""
        src = (Path(__file__).resolve().parents[1] / "backend" / "modules"
               / "router" / "ollama_client.py").read_text(encoding="utf-8")
        assert "OLLAMA_THINKING" not in src


class TestTheSwitchReachesTheModel:
    def test_it_is_added_to_the_system_prompt(self, monkeypatch):
        monkeypatch.setattr(config, "OLLAMA_THINK", "")
        msgs = oc._build_messages("You are Plasma.", [], "why", "qwen3:8b")
        assert msgs[0]["role"] == "system"
        assert oc.NO_THINK in msgs[0]["content"]
        assert "You are Plasma." in msgs[0]["content"]

    def test_a_plain_model_gets_the_prompt_unchanged(self, monkeypatch):
        monkeypatch.setattr(config, "OLLAMA_THINK", "")
        msgs = oc._build_messages("You are Plasma.", [], "why", "llama3.2:3b")
        assert msgs[0]["content"] == "You are Plasma."

    def test_it_works_with_no_system_prompt_at_all(self, monkeypatch):
        monkeypatch.setattr(config, "OLLAMA_THINK", "")
        msgs = oc._build_messages(None, [], "why", "qwen3:8b")
        assert msgs[0]["content"] == oc.NO_THINK

    def test_both_call_paths_pass_the_model_through(self):
        """chat() and chat_first_sentence() both build messages, and a switch
        applied to only one of them is worse than none — the same question
        would behave differently depending on which path ran."""
        src = (Path(__file__).resolve().parents[1] / "backend" / "modules"
               / "router" / "ollama_client.py").read_text(encoding="utf-8")
        assert src.count("_build_messages(system_prompt, history, user_message, model)") == 2

    def test_it_is_a_prompt_switch_not_an_api_field(self):
        """Ollama rejects think:false outright for models with no thinking
        mode, so keying off the API field would break every plain model to
        tidy up one. A stray token in a prompt is inert."""
        assert oc.NO_THINK.startswith("/")


class TestTheBudget:
    def test_there_is_room_for_a_real_answer(self):
        """160 was set when the budget was all answer. Even without thinking
        it is thin for "explain X"."""
        assert config.OLLAMA_NUM_PREDICT >= 240

    def test_it_is_still_a_voice_assistant(self):
        """Every extra token costs generation time AND speech time, twice
        over. This is not a chat window."""
        assert config.OLLAMA_NUM_PREDICT <= 600
