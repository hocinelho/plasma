"""Tests for the USER.md writer."""
import pytest
from backend.modules.user import user_md as um
from backend.modules.memory.store import MemoryStore


@pytest.fixture
def memory(tmp_path):
    return MemoryStore(db_path=tmp_path / "test.sqlite")


@pytest.fixture
def isolated_user_md(tmp_path, monkeypatch):
    """Redirect USER.md to a tmp file per test."""
    p = tmp_path / "USER.md"
    monkeypatch.setattr(um, "USER_MD_PATH", p)
    return p


def test_creates_file_if_missing(memory, isolated_user_md):
    assert not isolated_user_md.exists()
    um.write_user_md(memory=memory)
    assert isolated_user_md.exists()
    content = isolated_user_md.read_text(encoding="utf-8")
    assert "# USER.md" in content
    assert um.AUTO_START in content
    assert um.AUTO_END in content


def test_rewrites_facts_in_second_person(memory, isolated_user_md):
    memory.add_fact("identity", "My name is Hocine")
    memory.add_fact("preference", "I love strong coffee")
    um.write_user_md(memory=memory)
    content = isolated_user_md.read_text(encoding="utf-8")
    assert "Your name is Hocine" in content
    assert "You love strong coffee" in content
    assert "My name is" not in content


def test_preserves_user_edits_outside_auto_block(memory, isolated_user_md):
    # Initial write
    memory.add_fact("identity", "I am Hocine")
    um.write_user_md(memory=memory)

    # Simulate user editing the file: add a custom section ABOVE the auto block
    content = isolated_user_md.read_text(encoding="utf-8")
    custom = "## My handwritten notes\n- This is my own content.\n\n"
    patched = content.replace(um.AUTO_START, custom + um.AUTO_START)
    isolated_user_md.write_text(patched, encoding="utf-8")

    # Add a new fact and regenerate
    memory.add_fact("preference", "I prefer short replies")
    um.write_user_md(memory=memory)

    # Custom section must still be there, AND the new fact must appear
    final = isolated_user_md.read_text(encoding="utf-8")
    assert "My handwritten notes" in final
    assert "This is my own content." in final
    assert "You prefer short replies" in final


def test_no_facts_produces_placeholder(memory, isolated_user_md):
    um.write_user_md(memory=memory)
    content = isolated_user_md.read_text(encoding="utf-8")
    assert "No facts stored yet" in content