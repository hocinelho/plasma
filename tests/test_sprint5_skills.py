"""Tests for Sprint 5 skills: PA-57 wikipedia, PA-58 translator, PA-59 reminder."""
from __future__ import annotations


# ── PA-57 Wikipedia Lookup ────────────────────────────────────────────────────

def test_wikipedia_self_test():
    from backend.skills.wikipedia_lookup import self_test
    assert self_test()

def test_wikipedia_declines_with_no_topic():
    """"who is" on its own names nothing to look up. Declining hands it to
    the LLM, which can ask what they meant in context."""
    from backend.skills.wikipedia_lookup import run
    assert run({"utterance": "who is"}) is None

def test_wikipedia_first_sentence_single():
    from backend.skills.wikipedia_lookup import _first_sentence
    assert _first_sentence("Einstein was a physicist.") == "Einstein was a physicist."

def test_wikipedia_first_sentence_multi():
    from backend.skills.wikipedia_lookup import _first_sentence
    s = _first_sentence("Albert Einstein was a physicist. He developed relativity.")
    assert s == "Albert Einstein was a physicist."

def test_wikipedia_strip_who_is():
    from backend.skills.wikipedia_lookup import _STRIP
    assert _STRIP.sub("", "who is Albert Einstein").strip() == "Albert Einstein"

def test_wikipedia_strip_tell_me_about():
    from backend.skills.wikipedia_lookup import _STRIP
    assert _STRIP.sub("", "tell me about black holes").strip() == "black holes"

def test_wikipedia_strip_who_invented():
    from backend.skills.wikipedia_lookup import _STRIP
    assert _STRIP.sub("", "who invented the telephone").strip() == "the telephone"


# ── PA-58 Translator ──────────────────────────────────────────────────────────

def test_translator_self_test():
    from backend.skills.translator import self_test
    assert self_test()

def test_translator_parse_say_in():
    from backend.skills.translator import _detect_lang_from_utterance
    result = _detect_lang_from_utterance("say hello in French")
    assert result is not None
    phrase, lang = result
    assert phrase.lower() == "hello"
    assert lang == "french"

def test_translator_parse_translate_to():
    from backend.skills.translator import _detect_lang_from_utterance
    result = _detect_lang_from_utterance("translate good morning to Spanish")
    assert result is not None
    phrase, lang = result
    assert "good morning" in phrase.lower()
    assert lang == "spanish"

def test_translator_parse_how_do_you_say():
    from backend.skills.translator import _detect_lang_from_utterance
    result = _detect_lang_from_utterance("how do you say thank you in Japanese")
    assert result is not None
    assert result[1] == "japanese"

def test_translator_declines_a_language_it_cannot_do():
    """None means "not mine" — the router then sends it to the LLM, which can
    at least say something useful about Klingon. It used to answer with a
    canned "try saying it this way", which is a phrasebook, not an
    assistant."""
    from backend.skills.translator import run
    assert run({"utterance": "say hello in Klingon"}) is None

def test_translator_declines_when_no_language_is_named():
    """"say " has to be a trigger — "say hello in French" is the natural
    phrasing — and it also sits inside "why do you say that"."""
    from backend.skills.translator import run
    assert run({"utterance": "what is the weather"}) is None

def test_translator_lang_codes_complete():
    from backend.skills.translator import _LANG_CODES
    for lang in ("french", "spanish", "german", "japanese", "arabic"):
        assert lang in _LANG_CODES


# ── PA-59 Reminder ────────────────────────────────────────────────────────────

def test_reminder_self_test():
    from backend.skills.reminder import self_test
    assert self_test()

def test_reminder_relative_minutes():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me in 10 minutes to call Bob"})
    assert "10 minute" in r and "call Bob" in r

def test_reminder_relative_hours():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me in 2 hours to take medication"})
    assert "2 hour" in r and "medication" in r

def test_reminder_relative_seconds():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me in 30 seconds to check the oven"})
    assert "30 second" in r

def test_reminder_relative_compound():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me in 1 hour 30 minutes to stretch"})
    assert "1 hour" in r and "30 minute" in r

def test_reminder_absolute_pm():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me at 3pm to drink water"})
    assert "remind" in r.lower() and "drink water" in r

def test_reminder_absolute_24h():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me at 15:30 to leave the office"})
    assert "remind" in r.lower() and "leave the office" in r

def test_reminder_no_duration():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me"})
    assert "Try" in r or "didn't catch" in r.lower()

def test_reminder_zero_duration():
    from backend.skills.reminder import run
    r = run({"utterance": "remind me in 0 minutes to do something"})
    # zero duration should return error message
    assert "Try" in r or "didn't catch" in r.lower() or "remind" in r.lower()
