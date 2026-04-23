"""
Plasma skill registry — auto-loads Python skills from .plasma/skills/.

Each skill file must expose:
  - META: dict with at least {name, description, triggers}
  - run(args: dict) -> str
  - self_test() -> bool   (optional but recommended)

On load:
  1. Import every *.py file under .plasma/skills/
  2. Run self_test() if present — fail = skill disabled
  3. Register metadata into the skills_meta SQLite table for persistence
  4. Keep the loaded `run` function in memory for fast execution

This is the "same-process" execution model (Option A): skills share the
Plasma Python process. Fast but a crashing skill could take Plasma down.
We mitigate by running self_test at load time.
"""
from __future__ import annotations
import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.modules.memory.store import MemoryStore

log = logging.getLogger("plasma.skills")

# Locate .plasma/skills/ relative to project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_ROOT / "backend" / "skills"


@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str]
    run: Callable[[dict], str]
    file_path: str

    def invoke(self, args: Optional[dict] = None) -> str:
        try:
            return self.run(args or {})
        except Exception as e:
            log.exception(f"Skill '{self.name}' raised: {e}")
            return f"(Skill {self.name} failed: {e})"


class SkillRegistry:
    def __init__(self, memory: Optional[MemoryStore] = None):
        self._skills: dict[str, Skill] = {}
        self._memory = memory or MemoryStore()

    def load_all(self) -> int:
        """Discover and load every skill file. Return the number loaded."""
        if not SKILLS_DIR.exists():
            log.warning(f"Skills dir does not exist: {SKILLS_DIR}")
            return 0

        skill_files = sorted(SKILLS_DIR.glob("*.py"))
        loaded = 0
        for f in skill_files:
            if f.name.startswith("_"):
                continue
            if self._load_one(f):
                loaded += 1
        log.info(f"Skills loaded: {loaded}/{len(skill_files)}")
        return loaded

    def _load_one(self, path: Path) -> bool:
        try:
            spec = importlib.util.spec_from_file_location(
                f"plasma_skill_{path.stem}", path
            )
            if spec is None or spec.loader is None:
                log.error(f"Could not build spec for {path}")
                return False
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            meta = getattr(module, "META", None)
            run = getattr(module, "run", None)
            if not meta or not callable(run):
                log.warning(f"Skipping {path.name}: missing META or run()")
                return False

            name = meta.get("name") or path.stem
            description = meta.get("description", "")
            triggers = list(meta.get("triggers", []))

            # Unit-test gate
            self_test = getattr(module, "self_test", None)
            if callable(self_test):
                try:
                    if not self_test():
                        log.error(f"Skill '{name}' failed self_test — NOT loaded")
                        return False
                except Exception as e:
                    log.exception(f"Skill '{name}' self_test crashed: {e}")
                    return False

            # Register in memory DB for skill-search queries
            self._memory.register_skill(
                name=name,
                description=description,
                triggers=triggers,
                file_path=str(path),
            )

            self._skills[name] = Skill(
                name=name,
                description=description,
                triggers=triggers,
                run=run,
                file_path=str(path),
            )
            log.info(f"Loaded skill: {name}  triggers={triggers}")
            return True
        except Exception as e:
            log.exception(f"Failed to load skill {path}: {e}")
            return False

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def find_by_trigger(self, utterance: str) -> Optional[Skill]:
        """Naive keyword match: longest-trigger-wins."""
        lowered = utterance.lower()
        best: Optional[Skill] = None
        best_len = 0
        for skill in self._skills.values():
            for trig in skill.triggers:
                if trig.lower() in lowered and len(trig) > best_len:
                    best = skill
                    best_len = len(trig)
        return best


# Module-level singleton
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.load_all()
    return _registry