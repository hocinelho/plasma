"""Tests for weather city parsing.

Both bugs below were caught in live use: "what's the weather today?" reported
the weather for a village called Todaya, and asking for "Athens, Deutschland"
silently answered for the default city instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.skills import weather  # noqa: E402


def test_self_test_passes():
    assert weather.self_test() is True


@pytest.mark.parametrize("utterance", [
    "what's the weather today?",
    "Hi Plasma, what's the weather today?",
    "how is the weather",
    "weather outside",
    "what's the weather right now",
    "wie ist das wetter",
    "wetter heute",
])
def test_time_words_are_not_treated_as_cities(utterance):
    """'today' is not a place — must fall back to the default, not geocode it."""
    assert weather._parse_city(utterance) is None


@pytest.mark.parametrize("utterance,city", [
    ("weather in Paris", "Paris"),
    ("what's the weather in Athens?", "Athens"),
    ("what's the weather in New York today", "New York"),
    ("wetter in Berlin", "Berlin"),
])
def test_plain_cities_are_extracted(utterance, city):
    assert weather._parse_city(utterance) == city


@pytest.mark.parametrize("utterance", [
    "what's the weather in Athens, Greece?",
    "In Athens, what's the weather in Athens, Deutschland?",
    "weather in Athens, Dogeland?",     # as Whisper actually transcribed it
])
def test_city_with_country_is_not_silently_dropped(utterance):
    """A comma used to break the match entirely, defaulting to the wrong city."""
    assert weather._parse_city(utterance) == "Athens"


def test_unparseable_input_falls_back_rather_than_crashing():
    assert weather._parse_city("") is None
    assert weather._parse_city("tell me a joke") is None
