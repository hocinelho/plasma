"""A reasoning model must not read its own deliberation out loud.

Qwen3 is a hybrid reasoning model: it writes <think>...</think> before the
answer. Unhandled, Piper speaks the model's private working-out, the chat
shows it, and it eats the OLLAMA_NUM_PREDICT budget — so the reply gets
truncated by the thinking that preceded it.
"""
import pytest

from backend.core.config import config
from backend.modules.router.chat_service import strip_reasoning


class TestStripping:
    def test_a_normal_reply_is_untouched(self):
        assert strip_reasoning("It is 18 degrees in Moers.") == \
            "It is 18 degrees in Moers."

    def test_the_thinking_goes_and_the_answer_stays(self):
        raw = ("<think>The user asked about the weather. I should check "
               "the city they mentioned.</think>It is 18 degrees in Moers.")
        assert strip_reasoning(raw) == "It is 18 degrees in Moers."

    def test_thinking_after_the_answer_goes_too(self):
        raw = "Yes.<think>Should I add detail? No, they asked yes or no.</think>"
        assert strip_reasoning(raw) == "Yes."

    def test_several_blocks(self):
        raw = "<think>a</think>First.<think>b</think> Second."
        assert strip_reasoning(raw) == "First. Second."

    def test_an_unterminated_block_is_dropped(self):
        """num_predict cuts the reply mid-thought — everything from the tag on
        is reasoning, and there is no closing tag to match."""
        raw = "Here is the answer.<think>Now let me double check whether"
        assert strip_reasoning(raw) == "Here is the answer."

    def test_case_and_newlines(self):
        raw = "<THINK>\nline one\nline two\n</THINK>\nDone."
        assert strip_reasoning(raw) == "Done."

    def test_thinking_only_returns_something_rather_than_silence(self):
        """If the whole reply was thinking, saying nothing at all is worse."""
        raw = "<think>I am not sure what they mean.</think>"
        assert strip_reasoning(raw).strip() != ""

    def test_empty_and_none_are_safe(self):
        assert strip_reasoning("") == ""
        assert strip_reasoning(None) is None

    def test_a_lone_angle_bracket_is_not_mangled(self):
        assert strip_reasoning("Use a < b to compare.") == "Use a < b to compare."


class TestThinkFlag:
    """Ollama rejects `think` for models with no thinking mode, so it is only
    sent when the user has explicitly chosen."""

    @pytest.fixture
    def restore(self):
        before = config.OLLAMA_THINK
        yield
        config.OLLAMA_THINK = before

    def test_not_sent_by_default(self, restore):
        pytest.importorskip("httpx")
        from backend.modules.router import ollama_client as oc
        config.OLLAMA_THINK = ""
        assert "think" not in oc._payload("m", [], stream=False)

    def test_disabled_when_asked(self, restore):
        pytest.importorskip("httpx")
        from backend.modules.router import ollama_client as oc
        config.OLLAMA_THINK = "false"
        assert oc._payload("m", [], stream=False)["think"] is False

    def test_enabled_when_asked(self, restore):
        pytest.importorskip("httpx")
        from backend.modules.router import ollama_client as oc
        config.OLLAMA_THINK = "true"
        assert oc._payload("m", [], stream=False)["think"] is True


def test_both_llm_paths_strip():
    """Cloud and local alike — some hosted models think out loud too."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "backend" / "modules"
           / "router" / "chat_service.py").read_text(encoding="utf-8")
    assert src.count("return strip_reasoning(reply)") == 2
