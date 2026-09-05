"""Tests for passive learning — extract, classify, deduplicate."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.memory import learner  # noqa: E402
from backend.modules.memory.store import MemoryStore  # noqa: E402


@pytest.fixture
def memory():
    return MemoryStore(db_path=Path(tempfile.mkdtemp()) / "test.sqlite")


# ── similarity ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [
    ("Works at Vodafone", "Works at Vodafone as a field engineer"),
    ("Likes strong coffee", "Enjoys strong Algerian coffee"),
    ("Prefers strong coffee", "Likes strong coffee"),
    ("Lives in Moers", "Lives in Moers, Germany"),
])
def test_restatements_are_recognised_as_the_same_fact(a, b):
    assert learner.similarity(a, b) >= learner.DUPLICATE_THRESHOLD


@pytest.mark.parametrize("a,b", [
    # Sharing words is not saying the same thing.
    ("Works at Vodafone in Moers", "Lives in Moers near the Vodafone office"),
    ("Likes coffee", "Bought a coffee machine and a car"),
    ("Likes coffee", "Lives in Moers"),
    ("Speaks German", "Speaks French"),
    # These are the dangerous ones: a looser threshold would delete one of
    # each pair, losing a real fact about a different person or day.
    ("Has a brother named Ali", "Has a sister named Ali"),
    ("Meeting on Monday at nine", "Meeting on Friday at nine"),
])
def test_different_facts_are_never_merged(a, b):
    assert learner.similarity(a, b) < learner.DUPLICATE_THRESHOLD


def test_a_single_word_fact_does_not_match_everything():
    """One-word facts would otherwise be 'contained' in any longer fact."""
    assert learner.similarity("coffee", "Bought a coffee machine") < \
        learner.DUPLICATE_THRESHOLD


def test_similarity_is_symmetric():
    a, b = "Works at Vodafone", "Works at Vodafone as an engineer"
    assert learner.similarity(a, b) == learner.similarity(b, a)


def test_empty_input_is_not_a_match():
    assert learner.similarity("", "anything") == 0.0
    assert learner.similarity("anything", "") == 0.0


# ── parsing the model's output ───────────────────────────────────────────
def test_parses_a_fenced_json_array():
    raw = '```json\n[{"fact":"Works at Vodafone","category":"work"}]\n```'
    assert learner._parse(raw) == [{"fact": "Works at Vodafone", "category": "work"}]


def test_parses_an_array_wrapped_in_prose():
    raw = 'Sure: [{"fact":"Lives in Moers","category":"identity"}] hope that helps'
    assert learner._parse(raw)[0]["fact"] == "Lives in Moers"


def test_unknown_categories_are_coerced():
    raw = '[{"fact":"Something durable here","category":"astrology"}]'
    assert learner._parse(raw)[0]["category"] == "other"


def test_bare_strings_are_accepted():
    assert learner._parse('["Works at Vodafone"]')[0]["category"] == "other"


def test_too_short_facts_are_dropped():
    assert learner._parse('[{"fact":"ok","category":"other"}]') == []


def test_unparseable_output_yields_nothing():
    assert learner._parse("I could not find any facts.") == []
    assert learner._parse("") == []


def test_extraction_returns_nothing_for_trivial_messages():
    assert learner.extract_facts("ok") == []
    assert learner.extract_facts("") == []


# ── learning into the store ──────────────────────────────────────────────
def test_new_facts_are_stored_with_their_category(memory, monkeypatch):
    monkeypatch.setattr(learner, "extract_facts", lambda m: [
        {"fact": "Works at Vodafone", "category": "work"},
        {"fact": "Lives in Moers", "category": "identity"},
    ])
    results = learner.learn_from("anything", speaker="Hocine", memory=memory)
    assert [r["action"] for r in results] == ["added", "added"]
    stored = {f["content"]: f["category"] for f in memory.get_facts(user="Hocine")}
    assert stored["Works at Vodafone"] == "work"
    assert stored["Lives in Moers"] == "identity"


def test_repeating_yourself_does_not_duplicate_memory(memory, monkeypatch):
    monkeypatch.setattr(learner, "extract_facts", lambda m: [
        {"fact": "Likes strong coffee", "category": "preference"},
    ])
    learner.learn_from("x", speaker="Hocine", memory=memory)
    results = learner.learn_from("x again", speaker="Hocine", memory=memory)
    assert results[0]["action"] == "skipped"
    assert len(memory.get_facts(user="Hocine")) == 1


def test_a_more_detailed_restatement_replaces_the_vaguer_one(memory, monkeypatch):
    monkeypatch.setattr(learner, "extract_facts",
                        lambda m: [{"fact": "Works at Vodafone", "category": "work"}])
    learner.learn_from("x", speaker="Hocine", memory=memory)

    monkeypatch.setattr(learner, "extract_facts", lambda m: [
        {"fact": "Works at Vodafone as a field engineer", "category": "work"},
    ])
    results = learner.learn_from("y", speaker="Hocine", memory=memory)

    assert results[0]["action"] == "updated"
    contents = [f["content"] for f in memory.get_facts(user="Hocine")]
    assert contents == ["Works at Vodafone as a field engineer"]


def test_facts_are_kept_per_speaker(memory, monkeypatch):
    monkeypatch.setattr(learner, "extract_facts",
                        lambda m: [{"fact": "Drinks only tea", "category": "preference"}])
    learner.learn_from("x", speaker="Ali", memory=memory)
    assert any(f["content"] == "Drinks only tea"
               for f in memory.get_facts(user="Ali"))


def test_nothing_is_stored_when_extraction_finds_nothing(memory, monkeypatch):
    monkeypatch.setattr(learner, "extract_facts", lambda m: [])
    assert learner.learn_from("hello", speaker="Hocine", memory=memory) == []
    assert memory.get_facts(user="Hocine") == []


def test_learning_survives_extraction_blowing_up(memory, monkeypatch):
    """It runs unattended in the background — it must not raise."""
    def boom(_):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(learner, "extract_facts", boom)
    assert learner.learn_from("x", speaker="Hocine", memory=memory) == []
    assert memory.get_facts(user="Hocine") == []


def test_extraction_swallows_an_unreachable_model(monkeypatch):
    import backend.modules.router.chat_service as chat_service

    def boom(**kwargs):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(chat_service, "_llm_reply", boom)
    assert learner.extract_facts("a reasonably long sentence here") == []


# ── cleaning up what is already stored ───────────────────────────────────
def test_existing_duplicates_can_be_collapsed(memory):
    memory.add_fact(category="work", content="Works at Vodafone", user="Hocine")
    memory.add_fact(category="work", content="Works at Vodafone as an engineer",
                    user="Hocine")
    memory.add_fact(category="identity", content="Lives in Moers", user="Hocine")

    removed = learner.dedupe_existing(memory=memory, user="Hocine")
    assert removed == 1
    contents = sorted(f["content"] for f in memory.get_facts(user="Hocine"))
    assert contents == ["Lives in Moers", "Works at Vodafone"]


def test_dedupe_keeps_distinct_facts(memory):
    for content in ("Has a brother named Ali", "Has a sister named Ali",
                    "Speaks German", "Speaks French"):
        memory.add_fact(category="relationship", content=content, user="Hocine")
    assert learner.dedupe_existing(memory=memory, user="Hocine") == 0
    assert len(memory.get_facts(user="Hocine")) == 4
