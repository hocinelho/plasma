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
import re
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

    def invoke(self, args: Optional[dict] = None) -> Optional[str]:
        """Run the skill. None means "this was not for me".

        A trigger match is a guess made from a substring, and some of them
        have to be broad — "open ", "what is ", "play" — to catch the
        commands people actually say. The skill itself is the only place that
        can tell "open Chrome" from "open up to me", so it can decline by
        returning None and the router sends the utterance on to the LLM.

        The alternative, which is what happened before, is a confidently
        wrong answer from a skill that could not possibly help: "I want to
        play chess" answered by Spotify.
        """
        try:
            reply = self.run(args or {})
        except Exception as e:
            log.exception(f"Skill '{self.name}' raised: {e}")
            return f"(Skill {self.name} failed: {e})"
        if reply is None or (isinstance(reply, str) and not reply.strip()):
            log.info(f"Skill '{self.name}' declined — passing to the LLM")
            return None
        return reply


# Words that can precede a command without changing that it is one: her name,
# and the polite wrappers people put in front of a request out loud. Stripped
# before deciding whether a trigger STARTS the utterance, so "Plasma, can you
# open Chrome" is still an "open " command.
_ADDRESS = re.compile(
    r"^(?:\s*(?:hey|hi|hallo|ok|okay|yo)?\s*plasma\s*[,.!]?\s*"
    r"|\s*(?:please|bitte|could you|can you|would you|kannst du|könntest du)\s+)+",
    re.IGNORECASE,
)


def _matches_as_words(trigger: str, utterance: str) -> bool:
    """Does `trigger` appear in `utterance` as whole words?

    The point is to stop a trigger matching inside a longer word or midway
    through an unrelated sentence — "say " inside "why do you say that",
    "play" inside "I want to play chess". Both ends are anchored on a word
    boundary, so "start " still matches "start Chrome" and no longer matches
    "restart".

    A trailing space in a trigger is meaningful — "find a " wants a word
    after it — so it is kept as a required boundary rather than stripped.
    """
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in trigger.split()) + r"\b"
    if trigger.endswith(" "):
        pattern += r"\s"          # the trigger demands something after it
    return re.search(pattern, utterance) is not None


class SkillRegistry:
    def __init__(self, memory: Optional[MemoryStore] = None):
        self._skills: dict[str, Skill] = {}
        self._memory = memory or MemoryStore()

    def load_all(self) -> int:
        """Discover and load every skill file. Return the number loaded."""
        if not SKILLS_DIR.exists():
            log.warning(f"Skills dir does not exist: {SKILLS_DIR}")
            return 0

        skill_files = [f for f in sorted(SKILLS_DIR.glob("*.py")) if not f.name.startswith("_")]
        loaded = 0
        for f in skill_files:
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

            # Unit-test gate.
            #
            # self_test() normally calls run(), and some run()s have side
            # effects: tell_secret and show_abilities queue avatar movement.
            # Loading the skills therefore left "secret" plus the whole 19-clip
            # showcase waiting in the queue, and the first thing the user said
            # — "hello" — popped it and she performed her entire repertoire.
            #
            # The queue is cleared after every self_test rather than blocking
            # requests during it, because avatar_move's self_test legitimately
            # verifies that queueing works by queueing and popping.
            self_test = getattr(module, "self_test", None)
            if callable(self_test):
                from backend.modules import avatar_state
                try:
                    if not self_test():
                        log.error(f"Skill '{name}' failed self_test — NOT loaded")
                        return False
                except Exception as e:
                    log.exception(f"Skill '{name}' self_test crashed: {e}")
                    return False
                finally:
                    # Nothing a self-test staged is meant for the user.
                    avatar_state.clear()

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
        """Longest-trigger-wins, but only where the trigger is a real word.

        This used to be a plain substring test, and with 49 skills carrying
        prefixes as broad as "what is ", "say ", "play" and "start " it took
        most of ordinary conversation away from the LLM before it ever saw
        it. Measured against twenty natural sentences, eight were captured:

            "why do you say that"        -> translator
            "I want to play chess"       -> spotify_control
            "start over"                 -> open_app
            "how many hours should I sleep" -> unit_converter

        None of those is a command, and each got a confidently wrong answer
        from a skill that could not possibly help. That is what "if I say
        something outside the question he can't respond" is.

        A word-boundary test fixes the ones where the trigger landed inside
        or midway through a sentence. It cannot fix "what is your opinion"
        (calculator) — a command really can start that way — so a skill may
        also decline by returning None from run(), which sends the utterance
        on to the LLM; see chat_service.
        """
        lowered = utterance.lower()
        best: Optional[Skill] = None
        best_len = 0
        for skill in self._skills.values():
            for trig in skill.triggers:
                t = trig.lower().strip()
                if not t or len(t) <= best_len:
                    continue
                if _matches_as_words(t, lowered):
                    best, best_len = skill, len(t)
        return best


# Module-level singleton
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.load_all()
    return _registry