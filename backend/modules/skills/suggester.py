"""
Plasma skill suggester — pattern detector + proposal manager.

Watches every LLM-fallback turn (queries that didn't match a skill).
When 3+ similar queries accumulate, generates a proposal in
.plasma/skill_proposals.json. The user can approve / reject by voice.

Approving stamps the template into backend/skills/<name>.py and forces
a registry reload so the skill is available immediately.
"""
from __future__ import annotations
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from backend.modules.skills.templates import find_template_for, TEMPLATES, Template

log = logging.getLogger("plasma.suggester")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROPOSALS_PATH = PROJECT_ROOT / ".plasma" / "skill_proposals.json"
SKILLS_OUTPUT_DIR = PROJECT_ROOT / "backend" / "skills"

THRESHOLD = 3        # how many similar fallbacks before proposing
MAX_HISTORY = 50     # how many recent fallback turns to keep in memory


@dataclass
class FallbackTurn:
    utterance: str


@dataclass
class Proposal:
    id: str
    name: str
    template: str
    trigger_keywords: list[str]
    example_utterances: list[str] = field(default_factory=list)
    status: str = "pending"   # "pending" | "approved" | "rejected"

    def to_dict(self) -> dict:
        return asdict(self)


class SkillSuggester:
    def __init__(self):
        self._lock = threading.Lock()
        self._history: list[FallbackTurn] = []
        self._counts: dict[str, int] = {}  # template_name -> count
        self._examples: dict[str, list[str]] = {}  # template_name -> utterances
        PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ---------- pattern detection ----------
    def record_fallback(self, utterance: str) -> Optional[str]:
        """Log a fallback turn. Returns a nudge string if a new proposal was created."""
        utterance = (utterance or "").strip()
        if not utterance:
            return None

        tpl = find_template_for(utterance)
        if not tpl:
            return None

        with self._lock:
            self._history.append(FallbackTurn(utterance=utterance))
            if len(self._history) > MAX_HISTORY:
                self._history.pop(0)

            self._counts[tpl.name] = self._counts.get(tpl.name, 0) + 1
            self._examples.setdefault(tpl.name, []).append(utterance)
            self._examples[tpl.name] = self._examples[tpl.name][-5:]

            count = self._counts[tpl.name]
            log.info(f"Fallback recorded: tpl={tpl.name} count={count}")

            if count < THRESHOLD:
                return None

            # Check if this template already has an active proposal or is implemented
            if self._proposal_exists(tpl.name) or self._skill_exists(tpl.name):
                return None

            # Threshold hit — make a proposal
            proposal = self._create_proposal(tpl)
            return (
                f"\n\n(I noticed you've asked something I don't have a skill for "
                f"({tpl.name}) {count} times. Say 'approve {tpl.name} skill' to learn it, "
                f"or 'reject {tpl.name} skill' to dismiss.)"
            )

    def _create_proposal(self, tpl: Template) -> Proposal:
        proposals = self._read_proposals()
        new_id = f"p{len(proposals) + 1}"
        proposal = Proposal(
            id=new_id,
            name=tpl.name,
            template=tpl.name,
            trigger_keywords=tpl.default_triggers,
            example_utterances=list(self._examples.get(tpl.name, [])),
            status="pending",
        )
        proposals.append(proposal.to_dict())
        self._write_proposals(proposals)
        log.info(f"Proposal created: {proposal.name} (id={proposal.id})")
        return proposal

    # ---------- public ops ----------
    def list_proposals(self) -> list[dict]:
        return self._read_proposals()

    def approve(self, name_or_id: str) -> str:
        proposals = self._read_proposals()
        target = self._find_proposal(proposals, name_or_id)
        if not target:
            return f"I have no pending proposal for {name_or_id!r}."
        if target["status"] != "pending":
            return f"That proposal is already {target['status']}."

        # Find the template
        tpl = next((t for t in TEMPLATES if t.name == target["template"]), None)
        if not tpl:
            return f"I lost the template for {target['template']}. Please check the code."

        # Render and write the skill file
        triggers = target.get("trigger_keywords") or tpl.default_triggers
        code = tpl.render(triggers)

        out_path = SKILLS_OUTPUT_DIR / f"{target['name']}.py"
        if out_path.exists():
            target["status"] = "skipped"
            self._write_proposals(proposals)
            return f"A skill named {target['name']} already exists; proposal skipped."

        out_path.write_text(code, encoding="utf-8")

        # Mark approved
        target["status"] = "approved"
        self._write_proposals(proposals)

        # Force registry reload so the new skill is available now
        try:
            from backend.modules.skills import registry as reg_mod
            reg_mod._registry = None  # force re-init on next access
            new_count = len(reg_mod.get_registry().list())
            log.info(f"Registry reloaded; total skills now: {new_count}")
        except Exception as e:
            log.warning(f"Skill registry reload failed: {e}")

        return f"I've added the {target['name']} skill. Try it now."

    def reject(self, name_or_id: str) -> str:
        proposals = self._read_proposals()
        target = self._find_proposal(proposals, name_or_id)
        if not target:
            return f"I have no pending proposal for {name_or_id!r}."
        if target["status"] != "pending":
            return f"That proposal is already {target['status']}."
        target["status"] = "rejected"
        self._write_proposals(proposals)
        # Reset count so we don't immediately propose again
        with self._lock:
            self._counts[target["template"]] = 0
            self._examples.pop(target["template"], None)
        return f"Rejected the {target['name']} proposal."

    # ---------- helpers ----------
    def _read_proposals(self) -> list[dict]:
        if not PROPOSALS_PATH.exists():
            return []
        try:
            return json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Could not parse {PROPOSALS_PATH}: {e}")
            return []

    def _write_proposals(self, proposals: list[dict]) -> None:
        PROPOSALS_PATH.write_text(
            json.dumps(proposals, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _find_proposal(proposals: list[dict], key: str) -> Optional[dict]:
        key = key.lower().strip()
        for p in proposals:
            if p["id"].lower() == key or p["name"].lower() == key:
                return p
        return None

    def _proposal_exists(self, name: str) -> bool:
        for p in self._read_proposals():
            if p["name"] == name and p["status"] == "pending":
                return True
        return False

    def _skill_exists(self, name: str) -> bool:
        return (SKILLS_OUTPUT_DIR / f"{name}.py").exists()


# Singleton
_suggester: Optional[SkillSuggester] = None


def get_suggester() -> SkillSuggester:
    global _suggester
    if _suggester is None:
        _suggester = SkillSuggester()
    return _suggester