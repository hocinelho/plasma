"""Tests for PA-91 — Dictionary skill (all HTTP mocked)."""
from __future__ import annotations
from unittest.mock import MagicMock, patch


def _make_resp(json_data, status=200):
    r = MagicMock()
    r.raise_for_status.return_value = r
    r.json.return_value = json_data
    r.status_code = status
    return r


_DICT_RESP = [
    {
        "word": "ephemeral",
        "meanings": [
            {
                "partOfSpeech": "adjective",
                "definitions": [
                    {"definition": "Lasting for a very short time."},
                ],
            }
        ],
    }
]


# ── Word extraction ───────────────────────────────────────────────────────────

def test_extract_define():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("define ephemeral") == "ephemeral"

def test_extract_what_does_mean():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("what does resilience mean") == "resilience"

def test_extract_definition_of():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("definition of serendipity") == "serendipity"

def test_extract_meaning_of():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("meaning of ephemeral") == "ephemeral"

def test_extract_what_is_the_definition_of():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("what is the definition of perseverance") == "perseverance"

def test_extract_german_was_bedeutet():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("was bedeutet ephemeral") == "ephemeral"

def test_extract_german_was_heißt():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("was heißt ephemeral") == "ephemeral"

def test_extract_no_word_returns_none():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("what is the weather") is None

def test_extract_punctuation_stripped():
    from backend.skills.dictionary import _extract_word
    assert _extract_word("define ephemeral?") == "ephemeral"


# ── API calls ─────────────────────────────────────────────────────────────────

def test_run_returns_definition():
    from backend.skills.dictionary import run

    with patch("backend.skills.dictionary.http_get", return_value=_make_resp(_DICT_RESP)):
        result = run({"utterance": "define ephemeral"})

    assert "ephemeral" in result
    assert "adjective" in result
    assert "Lasting" in result


def test_run_word_not_found_404():
    from backend.skills.dictionary import run

    with patch("backend.skills.dictionary.http_get", return_value=_make_resp({}, status=404)):
        result = run({"utterance": "define zzzzqqqq"})

    assert "couldn't find" in result.lower()


def test_run_no_word_in_utterance():
    from backend.skills.dictionary import run

    result = run({"utterance": "tell me something"})
    assert "define" in result.lower() or "word" in result.lower() or "try" in result.lower()


def test_run_german_language_response():
    from backend.skills.dictionary import run

    with patch("backend.skills.dictionary.http_get", return_value=_make_resp(_DICT_RESP)):
        result = run({"utterance": "was bedeutet ephemeral", "language": "de"})

    assert "ephemeral" in result
    assert "Lasting" in result  # definition still in English


def test_run_german_not_found():
    from backend.skills.dictionary import run

    with patch("backend.skills.dictionary.http_get", return_value=_make_resp({}, status=404)):
        result = run({"utterance": "was bedeutet zzzzq", "language": "de"})

    assert "konnte" in result.lower() or "nicht" in result.lower()


def test_run_api_failure_graceful():
    from backend.skills.dictionary import run

    def failing_get(url, **kw):
        raise ConnectionError("offline")

    with patch("backend.skills.dictionary.http_get", side_effect=failing_get):
        result = run({"utterance": "define ephemeral"})

    assert "couldn't" in result.lower() or "reach" in result.lower()


def test_run_empty_meanings_graceful():
    from backend.skills.dictionary import run

    resp_no_meanings = [{"word": "test", "meanings": []}]
    with patch("backend.skills.dictionary.http_get", return_value=_make_resp(resp_no_meanings)):
        result = run({"utterance": "define test"})

    assert "no definition" in result.lower() or "couldn't" in result.lower()


def test_run_url_uses_lowercase_word():
    from backend.skills.dictionary import run
    captured = {}

    def fake_get(url, **kw):
        captured["url"] = url
        return _make_resp(_DICT_RESP)

    with patch("backend.skills.dictionary.http_get", side_effect=fake_get):
        run({"utterance": "define Ephemeral"})

    assert "ephemeral" in captured["url"]
    assert "Ephemeral" not in captured["url"]


def test_self_test():
    from backend.skills.dictionary import self_test
    assert self_test()


def test_meta_has_required_fields():
    from backend.skills.dictionary import META
    assert META["name"] == "dictionary"
    assert len(META["triggers"]) >= 5
    assert any("define" in t for t in META["triggers"])
    assert any("bedeutet" in t for t in META["triggers"])
