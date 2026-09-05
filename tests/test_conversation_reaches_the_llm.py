"""Ordinary conversation must reach the LLM.

Reported as: "he is not close to ChatGPT… not respond on why or what do you
think at all… if I say something not in the question he can't respond."

That was not the model being small. Skill triggers are matched as substrings
and, to catch the commands people actually say, some of them have to be as
broad as "what is ", "say ", "play" and "start ". With 49 skills loaded those
prefixes took most of ordinary conversation away from the LLM before it ever
saw it — and each capture produced a confident, useless answer from a skill
that could not possibly help.

Measured before the fix, on the twenty natural sentences below: NINE were
captured. "I want to play chess" was answered by Spotify. "start over" got a
list of installed applications. "what is your opinion on this" got a
calculator explaining that it only does arithmetic.

Two things fixed it, and both are needed. Triggers now match on word
boundaries, which rescues the ones where the trigger landed mid-sentence. And
a skill may return None to mean "not mine", which rescues the rest — a
command really can begin "what is", so only the skill itself can tell.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.INFO)

from backend.modules.skills.registry import SkillRegistry, _matches_as_words  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    r = SkillRegistry()
    r.load_all()
    return r


def _answers(registry, utterance: str):
    """What the skill layer would return, or None if it passes to the LLM."""
    skill = registry.find_by_trigger(utterance)
    if skill is None:
        return None
    return skill.invoke({"utterance": utterance, "language": "en"})


# Things a person says to an assistant they are talking WITH, not commanding.
CONVERSATION = [
    "what do you think about electric cars",
    "why is the sky blue",
    "what is your opinion on this",
    "tell me about yourself",
    "who is your favourite person",
    "can we talk about my day",
    "I had a rough day at work",
    "do you think I should quit my job",
    "what would you do in my place",
    "how many hours should I sleep",
    "say something nice",
    "start over",
    "I want to play chess",
    "let's play a game",
    "explain quantum computing to me",
    "why do you say that",
    "that's interesting, tell me more",
    "I disagree with you",
    "how does an engine work",
]

# ...and the commands that must keep working. Fixing the first list by
# loosening the triggers would have broken this one, which is the whole
# difficulty.
COMMANDS = [
    ("open chrome", "open_app"),
    ("what time is it", "get_time"),
    ("what is 12 times 4", "calculator"),
    ("set a timer for 5 minutes", "timer"),
    ("wave at me", "avatar_move"),
    ("turn around", "avatar_move"),
    ("what's the weather", "weather"),
    ("play music", "spotify_control"),
    ("how many kilometers is 5 miles", "unit_converter"),
    ("convert 5 miles to kilometers", "unit_converter"),
    ("tell me a joke", "joke"),
    ("say good morning in french", "translator"),
    ("tell me about Einstein", "wikipedia_lookup"),
    ("who is Marie Curie", "wikipedia_lookup"),
    ("can you see me", "vision_query"),
    ("turn off the lights", "smart_home"),
    ("take a screenshot", "screenshot"),
]


@pytest.mark.parametrize("utterance", CONVERSATION)
def test_conversation_is_not_captured_by_a_skill(registry, utterance):
    answer = _answers(registry, utterance)
    assert answer is None, (
        f"{utterance!r} was answered by a skill instead of reaching the LLM: "
        f"{answer!r}"
    )


@pytest.mark.parametrize("utterance,expected", COMMANDS)
def test_real_commands_still_route(registry, utterance, expected):
    skill = registry.find_by_trigger(utterance)
    assert skill is not None, f"{utterance!r} reached no skill at all"
    assert skill.name == expected, f"{utterance!r} went to {skill.name}"


class TestWordBoundaries:
    """A trigger has to be a word, not a run of letters."""

    def test_a_trigger_inside_a_longer_word_does_not_match(self):
        assert not _matches_as_words("start", "restart the computer")
        assert not _matches_as_words("play", "displaying the results")

    def test_it_still_matches_a_real_word(self):
        assert _matches_as_words("start", "start chrome")
        assert _matches_as_words("play music", "please play music now")

    def test_a_trailing_space_still_demands_a_word_after_it(self):
        """"find a " wants something to find; without the space rule it would
        match a sentence ending in "find a"."""
        assert _matches_as_words("find a ", "find a screwdriver")
        assert not _matches_as_words("find a ", "there is nothing to find")

    def test_internal_spacing_is_forgiving(self):
        assert _matches_as_words("turn off the lights", "turn off  the lights")


class TestDeclining:
    """The mechanism behind the second half of the fix."""

    def test_none_means_the_llm_should_answer(self, registry):
        skill = registry.get("calculator")
        assert skill.invoke({"utterance": "what is your opinion"}) is None

    def test_an_empty_reply_counts_as_declining(self, registry):
        """A skill that returns "" has said nothing; speaking silence is not
        an answer, and neither is an empty chat bubble."""
        from backend.modules.skills.registry import Skill
        s = Skill("t", "", [], lambda a: "   ", "x")
        assert s.invoke({}) is None

    def test_a_crash_is_still_reported_not_silently_passed_on(self, registry):
        """Declining and failing must stay distinguishable — a skill that
        raises has a bug, and hiding it behind an LLM answer would make it
        invisible."""
        from backend.modules.skills.registry import Skill

        def boom(_a):
            raise RuntimeError("kaboom")

        assert "failed" in Skill("t", "", [], boom, "x").invoke({})

    def test_the_router_falls_through_on_none(self):
        src = (Path(__file__).resolve().parents[1] / "backend" / "modules"
               / "router" / "chat_service.py").read_text(encoding="utf-8")
        block = src.split("Skill match:", 1)[1][:900]
        assert "if reply is not None:" in block
