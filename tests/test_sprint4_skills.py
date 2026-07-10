"""Tests for Sprint 4 skills: PA-53 timer, PA-54 calculator, PA-55 joke, PA-56 unit converter."""
from __future__ import annotations


# ── PA-53 Timer ───────────────────────────────────────────────────────────────

def test_timer_seconds():
    from backend.skills.timer import run
    assert "30 second" in run({"utterance": "set a timer for 30 seconds"})

def test_timer_minutes():
    from backend.skills.timer import run
    assert "5 minute" in run({"utterance": "set a timer for 5 minutes"})

def test_timer_hours():
    from backend.skills.timer import run
    assert "2 hour" in run({"utterance": "set a timer for 2 hours"})

def test_timer_compound():
    from backend.skills.timer import run
    r = run({"utterance": "timer for 1 minute 30 seconds"})
    assert "1m" in r or "minute" in r

def test_timer_no_duration():
    from backend.skills.timer import run
    r = run({"utterance": "set a timer"})
    assert "How long" in r

def test_timer_self_test():
    from backend.skills.timer import self_test
    assert self_test()


# ── PA-54 Calculator ──────────────────────────────────────────────────────────

def test_calc_times():
    from backend.skills.calculator import run
    assert run({"utterance": "what is 6 times 7"}) == "42."

def test_calc_plus():
    from backend.skills.calculator import run
    assert run({"utterance": "what is 100 plus 23"}) == "123."

def test_calc_minus():
    from backend.skills.calculator import run
    assert run({"utterance": "calculate 50 minus 8"}) == "42."

def test_calc_divided():
    from backend.skills.calculator import run
    assert run({"utterance": "how much is 100 divided by 4"}) == "25."

def test_calc_divide_by_zero():
    from backend.skills.calculator import run
    assert "zero" in run({"utterance": "what is 5 divided by 0"}).lower()

def test_calc_self_test():
    from backend.skills.calculator import self_test
    assert self_test()


# ── PA-55 Joke ────────────────────────────────────────────────────────────────

def test_joke_returns_string():
    from backend.skills.joke import run
    r = run({})
    assert isinstance(r, str) and len(r) > 10

def test_joke_varies():
    from backend.skills.joke import run
    results = {run({}) for _ in range(20)}
    assert len(results) > 1  # not always the same joke

def test_joke_self_test():
    from backend.skills.joke import self_test
    assert self_test()


# ── PA-56 Unit Converter ──────────────────────────────────────────────────────

def test_unit_km_to_miles():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 1 kilometer to miles"})
    assert "0.6214" in r or "0.621" in r

def test_unit_miles_to_km():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 1 mile to kilometers"})
    assert "1.609" in r

def test_unit_kg_to_pounds():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 1 kilogram to pounds"})
    assert "2.204" in r or "2.2" in r

def test_unit_celsius_to_fahrenheit():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 100 celsius to fahrenheit"})
    assert "212" in r

def test_unit_fahrenheit_to_celsius():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 32 fahrenheit to celsius"})
    assert "0" in r

def test_unit_incompatible():
    from backend.skills.unit_converter import run
    r = run({"utterance": "convert 5 miles to kilograms"})
    assert "Can't convert" in r

def test_unit_self_test():
    from backend.skills.unit_converter import self_test
    assert self_test()
