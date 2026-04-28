"""Tests for the skill suggester."""
import pytest
from pathlib import Path
from backend.modules.skills import suggester as sg


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect proposal storage and skills output dir to tmp."""
    monkeypatch.setattr(sg, "PROPOSALS_PATH", tmp_path / "proposals.json")
    skills_out = tmp_path / "skills"
    skills_out.mkdir()
    monkeypatch.setattr(sg, "SKILLS_OUTPUT_DIR", skills_out)
    sg._suggester = None  # force fresh singleton
    return tmp_path


def test_no_nudge_for_first_two_fallbacks(isolated):
    s = sg.get_suggester()
    assert s.record_fallback("what's the weather in moers") is None
    assert s.record_fallback("what's the weather in paris") is None


def test_nudge_on_third_matching_fallback(isolated):
    s = sg.get_suggester()
    s.record_fallback("what's the weather in moers")
    s.record_fallback("what's the weather in paris")
    nudge = s.record_fallback("what's the weather today")
    assert nudge is not None
    assert "weather" in nudge.lower()


def test_proposal_persisted(isolated):
    s = sg.get_suggester()
    for u in ["weather in a", "weather in b", "weather in c"]:
        s.record_fallback(u)
    proposals = s.list_proposals()
    assert len(proposals) == 1
    assert proposals[0]["name"] == "weather"
    assert proposals[0]["status"] == "pending"


def test_approve_creates_skill_file(isolated):
    s = sg.get_suggester()
    for u in ["weather in a", "weather in b", "weather in c"]:
        s.record_fallback(u)
    msg = s.approve("weather")
    assert "weather" in msg.lower()
    skill_file = sg.SKILLS_OUTPUT_DIR / "weather.py"
    assert skill_file.exists()
    code = skill_file.read_text(encoding="utf-8")
    assert 'META' in code and 'def run' in code


def test_reject_marks_proposal(isolated):
    s = sg.get_suggester()
    for u in ["tell me a joke", "another joke please", "joke time"]:
        s.record_fallback(u)
    msg = s.reject("joke")
    assert "rejected" in msg.lower()
    proposals = s.list_proposals()
    assert proposals[0]["status"] == "rejected"


def test_unrelated_query_does_not_trigger(isolated):
    s = sg.get_suggester()
    for u in ["why is the sky blue", "tell me about quantum physics", "what is consciousness"]:
        assert s.record_fallback(u) is None