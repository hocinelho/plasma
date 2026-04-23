"""Unit tests for the skill registry."""
import pytest
from backend.modules.skills.registry import SkillRegistry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A fresh registry in an isolated temp SQLite DB."""
    from backend.modules.memory.store import MemoryStore
    mem = MemoryStore(db_path=tmp_path / "test.sqlite")
    reg = SkillRegistry(memory=mem)
    reg.load_all()
    return reg


def test_registry_loads_get_time(registry: SkillRegistry):
    names = [s.name for s in registry.list()]
    assert "get_time" in names, f"Expected get_time in {names}"


def test_get_time_returns_string(registry: SkillRegistry):
    skill = registry.get("get_time")
    assert skill is not None
    result = skill.invoke()
    assert isinstance(result, str)
    assert result.startswith("It's ")
    assert ":" in result   # "HH:MM"


def test_trigger_matching(registry: SkillRegistry):
    assert registry.find_by_trigger("What time is it?").name == "get_time"
    assert registry.find_by_trigger("tell me the time please").name == "get_time"
    assert registry.find_by_trigger("unrelated question").name if registry.find_by_trigger("unrelated question") else None is None


def test_no_match_returns_none(registry: SkillRegistry):
    assert registry.find_by_trigger("hello how are you") is None