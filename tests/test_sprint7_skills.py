"""Tests for Sprint 7 skills: PA-60 voice notes, PA-61 todo list, PA-62 news RSS, PA-63 forecast."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path


# ── PA-60 Voice Notes ─────────────────────────────────────────────────────────

def test_voice_notes_self_test():
    from backend.skills.voice_notes import self_test
    assert self_test()

def _patched_notes(tmp_path):
    import backend.skills.voice_notes as mod
    mod._NOTES_FILE = Path(tmp_path) / "notes.jsonl"
    return mod

def test_voice_notes_save(tmp_path):
    mod = _patched_notes(tmp_path)
    r = mod.run({"utterance": "take a note: buy milk"})
    assert "buy milk" in r.lower()
    assert mod._read_all() == ["buy milk"]

def test_voice_notes_read(tmp_path):
    mod = _patched_notes(tmp_path)
    mod._save("test item")
    r = mod.run({"utterance": "read my notes"})
    assert "test item" in r.lower()

def test_voice_notes_read_empty(tmp_path):
    mod = _patched_notes(tmp_path)
    r = mod.run({"utterance": "show my notes"})
    assert "no" in r.lower()

def test_voice_notes_clear(tmp_path):
    mod = _patched_notes(tmp_path)
    mod._save("note one")
    mod.run({"utterance": "clear my notes"})
    assert mod._read_all() == []

def test_voice_notes_strip_trigger():
    from backend.skills.voice_notes import _STRIP
    assert _STRIP.sub("", "take a note: hello world").strip() == "hello world"
    assert _STRIP.sub("", "write down: meeting at 3").strip() == "meeting at 3"
    # Comma separator (how speech-to-text delivers it)
    assert _STRIP.sub("", "take a note, buy milk tomorrow").strip() == "buy milk tomorrow"

def test_voice_notes_meta():
    from backend.skills.voice_notes import META
    assert any("note" in t for t in META["triggers"])


# ── PA-61 Todo List ───────────────────────────────────────────────────────────

def test_todo_self_test():
    from backend.skills.todo_list import self_test
    assert self_test()

def _patched_todo(tmp_path):
    import backend.skills.todo_list as mod
    mod._TODO_FILE = Path(tmp_path) / "todos.json"
    return mod

def test_todo_add_natural(tmp_path):
    mod = _patched_todo(tmp_path)
    r = mod.run({"utterance": "add buy groceries to my list"})
    assert "buy groceries" in r.lower()

def test_todo_add_colon(tmp_path):
    mod = _patched_todo(tmp_path)
    r = mod.run({"utterance": "add to my list: call the doctor"})
    assert "call the doctor" in r.lower()

def test_todo_read(tmp_path):
    mod = _patched_todo(tmp_path)
    mod.run({"utterance": "add buy milk to my list"})
    r = mod.run({"utterance": "what's on my list"})
    assert "buy milk" in r.lower()

def test_todo_read_empty(tmp_path):
    mod = _patched_todo(tmp_path)
    r = mod.run({"utterance": "what's on my list"})
    assert "empty" in r.lower()

def test_todo_clear(tmp_path):
    mod = _patched_todo(tmp_path)
    mod.run({"utterance": "add something to my list"})
    mod.run({"utterance": "clear my list"})
    assert mod._load() == []

def test_todo_mark_done(tmp_path):
    mod = _patched_todo(tmp_path)
    mod.run({"utterance": "add buy milk to my list"})
    r = mod.run({"utterance": "mark as done: buy milk"})
    assert "done" in r.lower()
    items = mod._load()
    assert items[0]["done"] is True

def test_todo_meta():
    from backend.skills.todo_list import META
    assert any("list" in t for t in META["triggers"])


# ── PA-62 News RSS ────────────────────────────────────────────────────────────

def test_news_self_test():
    from backend.skills.news_disclaimer import self_test
    assert self_test()

def test_news_parse_single():
    from backend.skills.news_disclaimer import _parse_headlines
    xml = ('<?xml version="1.0"?><rss><channel>'
           '<item><title>Big story today</title></item>'
           '</channel></rss>')
    assert _parse_headlines(xml) == ["Big story today"]

def test_news_parse_multiple():
    from backend.skills.news_disclaimer import _parse_headlines
    xml = ('<?xml version="1.0"?><rss><channel>'
           '<item><title>Story one</title></item>'
           '<item><title>Story two</title></item>'
           '<item><title>Story three</title></item>'
           '<item><title>Story four</title></item>'
           '</channel></rss>')
    titles = _parse_headlines(xml, max_items=3)
    assert len(titles) == 3
    assert titles[0] == "Story one"

def test_news_parse_empty():
    from backend.skills.news_disclaimer import _parse_headlines
    xml = '<?xml version="1.0"?><rss><channel></channel></rss>'
    assert _parse_headlines(xml) == []

def test_news_meta():
    from backend.skills.news_disclaimer import META
    assert any("news" in t for t in META["triggers"])


# ── PA-63 Weather Forecast ────────────────────────────────────────────────────

def test_forecast_self_test():
    from backend.skills.weather_forecast import self_test
    assert self_test()

def test_forecast_meta():
    from backend.skills.weather_forecast import META
    assert any("forecast" in t for t in META["triggers"])
    assert any("week" in t for t in META["triggers"])

def test_forecast_city_regex():
    from backend.skills.weather_forecast import _CITY_RE
    m = _CITY_RE.search("weather forecast for Berlin")
    assert m and m.group(1).strip() == "Berlin"

def test_forecast_no_conflict_with_weather():
    """weather_forecast triggers should all be longer than 'weather' (7 chars)."""
    from backend.skills.weather_forecast import META
    for t in META["triggers"]:
        assert len(t) > 7, f"Trigger '{t}' would lose to 'weather' in routing"

def test_weather_routing_no_forecast_trigger():
    """weather.py must not contain 'weather forecast' after the S7 fix."""
    from backend.skills.weather import META as weather_meta
    assert "weather forecast" not in weather_meta["triggers"]
