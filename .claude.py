# Plasma — Claude Code Project Instructions

You are working on Plasma, a local-first voice assistant. Read these instructions BEFORE doing anything in this repo.

---

## Required reading order

1. This file
2. `.plasma/MEMORY.md` — full project state and decisions log
3. `HANDOFF.md` — current session priorities and unfinished cleanup
4. `README.md` — public roadmap

After reading those three, ask the user one question: **"What's next — Step 9, polish, or something else?"** Don't start coding without confirmation.

---

## Project conventions (don't break these)

### File creation
- Skill files live in `backend/skills/<name>.py` (NOT `backend/modules/skills/`)
- Skill framework code (registry, suggester, templates) lives in `backend/modules/skills/`
- Tests in `tests/test_<feature>.py`
- All new modules need an `__init__.py` (even if empty)

### Code style
- Type hints with `from __future__ import annotations`
- 4-space indentation, no tabs
- Use `pathlib.Path` for paths, never raw strings
- Logger names: `plasma.<module>` (e.g. `logging.getLogger("plasma.skills")`)

### Skill format
Every skill file in `backend/skills/` must export:
```python
META = {
    "name": "skill_name",
    "description": "Short description.",
    "triggers": ["phrase one", "phrase two"],   # case-insensitive substring match
}

def run(args: dict | None = None) -> str:
    return "..."

def self_test() -> bool:   # optional but recommended
    return True
```

The registry calls `self_test()` on load. Skills that fail their self-test are silently disabled.

### Testing
- Run `pytest tests/ -v` before every commit
- All 26 existing tests must pass
- New features must come with tests

### Git
- Commit after every logical step
- One conventional commit message format: `Step N: short description` or `Polish 8b: ...`
- Push after every commit
- Branch: `main` only — no feature branches for this project

### Security
- API keys ONLY in `.env` (which is gitignored)
- `.env.example` may contain placeholder values
- No secrets in chat, no secrets in any .md file
- All outbound network calls must be loggable in the planned `.plasma/audit.log` (Step 9)

---

## Don't do these things

- ❌ Don't push to feature branches like `claude/enhance-...` — push directly to `main`
- ❌ Don't use PowerShell `@"..."@` here-strings to create files — they break on Windows
- ❌ Don't commit `tts_test.wav`, `_clean_facts.py`, `_smoke_*.py`, or any scratch file
- ❌ Don't fine-tune the LLM weights — Plasma's "learning" happens in the context layer (USER.md, skills/, memory.sqlite), never the model
- ❌ Don't add cloud LLM dependencies before Step 9 is officially started
- ❌ Don't generate skill code via LLM until Step 9 lands a sandboxed approach
- ❌ Don't add features the user didn't ask for. The roadmap exists for a reason.

---

## Common tasks

### Add a new skill
1. Create `backend/skills/<name>.py` with META + run + self_test
2. Restart uvicorn (or wait for `--reload`)
3. Verify with `pytest tests/test_skills.py -v`
4. Test in voice via http://127.0.0.1:8000/
5. Commit

### Add a new module
1. Create the directory under `backend/modules/`
2. Add `__init__.py` (empty)
3. Add the module file with proper imports
4. Add a test file under `tests/`
5. Commit

### Fix a bug
1. Reproduce with `pytest` or curl
2. Write a failing test FIRST
3. Fix the code
4. Confirm test passes
5. Commit with `Fix: <description>`

---

## What "done" means for a step

A step is only done when ALL of these are true:
- [ ] Code is written and saved
- [ ] `pytest tests/ -v` passes (all 26+)
- [ ] Manual voice test passes (or HTTP test for non-voice features)
- [ ] `.plasma/MEMORY.md` is updated with the new commit + step entry
- [ ] Code is committed and pushed
- [ ] Anti-pattern check: no scratch files, no secrets, no broken imports

If any of these isn't true, the step is NOT done. Don't claim "done" prematurely.

---

## Communicating with the user

- The user is Hocine Bahri. Native speaker of French/Arabic, fluent technical English with German keyboard.
- He prefers: short replies, code blocks over prose, file paths absolute or repo-rooted, "step by step" pacing.
- He gets frustrated when: Plasma hallucinates, Whisper mishears him, or steps stall on yak-shaving.
- When in doubt, ask one question with `ask_user_input_v0` rather than assuming.

---

## Latency targets (current vs goal)

| Path | Current (CPU) | Goal | How |
|---|---|---|---|
| Skill match → reply | 5–8s | 2–3s | Whisper streaming + skill-first routing (Step 8 done) |
| LLM fallback | 10–30s | 3–5s | Step 9: cloud LLM with PII redaction |
| Cold start (uvicorn launch → ready) | 15s | 5s | Step 9 deferred warmup |
| Wake-word recognition | N/A (push-to-talk) | <300ms | Step 8c: custom "hey plasma" model |

---

## Useful one-liners

```powershell
# What's loaded in Ollama RAM
ollama ps

# What memory facts does Plasma have
python -c "from backend.modules.memory.store import MemoryStore; m = MemoryStore(); [print(f) for f in m.get_facts(limit=100)]"

# What skills are registered
python -c "from backend.modules.skills.registry import get_registry; print([s.name for s in get_registry().list()])"

# Force USER.md rebuild
Invoke-RestMethod -Method POST http://127.0.0.1:8000/user/reflect

# List skill proposals
Invoke-RestMethod http://127.0.0.1:8000/skills/proposals | ConvertTo-Json -Depth 5
```

---

## When you finish a session

Update `.plasma/MEMORY.md` with:
- New "Last updated" timestamp
- Updated step status table
- New commit hashes
- Anything you tried that didn't work (under "Anti-patterns to avoid")

This is the contract between sessions. Without it, the next agent starts from scratch.