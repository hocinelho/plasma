"""Tests for the Ollama request knobs that decide how fast she feels.

These are one-line settings that are invisible when wrong: nothing errors, she
is just slow. keep_alive in particular only shows up as a problem after five
minutes of silence, which is exactly when nobody is watching the logs.
"""
import pytest

pytest.importorskip("httpx")

from backend.core.config import config
from backend.modules.router import ollama_client as oc


@pytest.fixture
def restore_config():
    before = (config.OLLAMA_KEEP_ALIVE, config.OLLAMA_NUM_PREDICT, config.OLLAMA_NUM_CTX)
    yield
    (config.OLLAMA_KEEP_ALIVE, config.OLLAMA_NUM_PREDICT, config.OLLAMA_NUM_CTX) = before


def test_keep_alive_is_sent_on_every_request():
    """Ollama unloads an idle model after 5 minutes; the startup warm-up alone
    does not survive a lunch break."""
    for stream in (True, False):
        assert oc._payload("m", [], stream=stream)["keep_alive"] == config.OLLAMA_KEEP_ALIVE


def test_reply_length_is_capped():
    """A spoken answer costs time twice — generating it and saying it."""
    assert oc._payload("m", [], stream=False)["options"]["num_predict"] == \
        config.OLLAMA_NUM_PREDICT


def test_zero_disables_the_cap_rather_than_silencing_her(restore_config):
    """num_predict=0 means 'generate nothing' to Ollama, so 0 must mean
    'send no cap at all' here, not 'send zero'."""
    config.OLLAMA_NUM_PREDICT = 0
    config.OLLAMA_NUM_CTX = 0
    assert "options" not in oc._payload("m", [], stream=False)


def test_context_window_is_left_alone_by_default(restore_config):
    """A bigger window costs memory and slows every token — opt in only."""
    config.OLLAMA_NUM_PREDICT = 160
    config.OLLAMA_NUM_CTX = 0
    assert "num_ctx" not in oc._payload("m", [], stream=False)["options"]

    config.OLLAMA_NUM_CTX = 8192
    assert oc._payload("m", [], stream=False)["options"]["num_ctx"] == 8192


def test_both_call_paths_share_the_builder():
    """Streaming and blocking must not drift apart — the whole point of the
    shared builder is that a knob added once applies to both."""
    src = (oc.__file__)
    text = open(src, encoding="utf-8").read()
    assert text.count("_payload(model, messages, stream=") == 2
    assert '"stream": False}' not in text     # no hand-rolled payload left
    assert '"stream": True}' not in text
