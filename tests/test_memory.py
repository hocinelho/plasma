"""Tests for the SQLite FTS5 memory store."""
import pytest
from pathlib import Path
from backend.modules.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    """Fresh in-tmp-dir database per test — no state leaks."""
    return MemoryStore(db_path=tmp_path / "test.sqlite")


# ----- Conversations ---------------------------------------------------
def test_add_and_get_conversation(store: MemoryStore):
    sid = "sess-1"
    store.add_message(sid, "user", "Hello Plasma")
    store.add_message(sid, "assistant", "Hi Hocine, how can I help?")
    store.add_message(sid, "user", "Remind me to test FTS later")

    msgs = store.get_conversation(sid)
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello Plasma"
    assert msgs[1]["role"] == "assistant"


def test_search_conversations_fts(store: MemoryStore):
    store.add_message("sess-1", "user", "I love fiber optic OTDR traces")
    store.add_message("sess-1", "assistant", "Sure, what would you like to know about OTDR?")
    store.add_message("sess-2", "user", "Tell me about cooking pasta")

    hits = store.search_conversations("OTDR")
    assert len(hits) == 2
    # pasta should not match
    hits2 = store.search_conversations("pasta")
    assert len(hits2) == 1
    assert "pasta" in hits2[0]["content"].lower()


def test_conversation_isolation_by_session(store: MemoryStore):
    store.add_message("a", "user", "a-message")
    store.add_message("b", "user", "b-message")
    assert len(store.get_conversation("a")) == 1
    assert len(store.get_conversation("b")) == 1


# ----- Facts -----------------------------------------------------------
def test_add_and_list_facts(store: MemoryStore):
    store.add_fact("preference", "User prefers concise answers", source="user_stated")
    store.add_fact("identity", "User is Hocine Bahri, based in Moers", source="user_stated")
    store.add_fact("project", "Currently working on Einblasen app", confidence=0.9)

    all_facts = store.get_facts()
    assert len(all_facts) == 3

    prefs = store.get_facts(category="preference")
    assert len(prefs) == 1
    assert "concise" in prefs[0]["content"]


def test_search_facts_fts(store: MemoryStore):
    store.add_fact("project", "Einblasen is a fiber optic monitoring PWA")
    store.add_fact("preference", "User works in PyCharm on Windows")
    store.add_fact("person", "Likes anime and 3D graphics")

    hits = store.search_facts("fiber")
    assert len(hits) >= 1
    assert "fiber" in hits[0]["content"].lower()


def test_delete_fact(store: MemoryStore):
    fid = store.add_fact("preference", "to be deleted")
    assert store.delete_fact(fid) is True
    assert store.delete_fact(fid) is False  # already gone


# ----- Skills ----------------------------------------------------------
def test_register_and_list_skills(store: MemoryStore):
    store.register_skill(
        name="send_email",
        description="Compose and send an email via Outlook",
        triggers=["email", "send message", "mail"],
        file_path=".plasma/skills/send_email.md",
    )
    store.register_skill(
        name="find_calendar_slot",
        description="Find a free slot in the next 7 days",
        triggers=["schedule", "free time", "book meeting"],
        file_path=".plasma/skills/find_calendar_slot.md",
    )
    skills = store.list_skills()
    assert len(skills) == 2
    names = {s["name"] for s in skills}
    assert {"send_email", "find_calendar_slot"} == names
    # triggers should be deserialized to a list
    assert isinstance(skills[0]["triggers"], list)


def test_search_skills(store: MemoryStore):
    store.register_skill(
        name="send_email",
        description="Compose and send an email via Outlook",
        triggers=["email", "send message"],
        file_path=".plasma/skills/send_email.md",
    )
    hits = store.search_skills("email")
    assert len(hits) == 1
    assert hits[0]["name"] == "send_email"


def test_mark_skill_used(store: MemoryStore):
    store.register_skill(
        name="test_skill",
        description="for testing",
        triggers=["test"],
        file_path="nowhere.md",
    )
    store.mark_skill_used("test_skill", success=True)
    store.mark_skill_used("test_skill", success=True)
    store.mark_skill_used("test_skill", success=False)

    skills = store.list_skills()
    s = next(x for x in skills if x["name"] == "test_skill")
    assert s["usage_count"] == 3
    # 2 successes out of 3
    assert abs(s["success_rate"] - (2 / 3)) < 0.01