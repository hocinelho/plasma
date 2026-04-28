# Plasma — Agent Handoff

Read this if you're a new agent (Claude Code, future Claude session, etc.) being asked to continue work on Plasma. After reading this and `.plasma/MEMORY.md`, you should have full context.

---

## Project in one sentence

Plasma is a working local-first voice assistant on Windows: hear (Whisper) → think (skills or local Ollama with USER.md context) → speak (Piper Ryan voice). 100% local, no cloud yet.

---

## Where we are right now

**Step 8b just finished.** Skill suggester works: when the user asks similar things 3+ times that no skill handles, Plasma generates a skill proposal from one of four templates (weather, calculator, joke, timer). The user approves by voice → the skill file is auto-written → registry reloads → next matching query hits the new skill in <1s.

**Live system test passed.** A `weather` skill was self-generated and used in production within the same session.

**Six commits make up Steps 1–8.** See `.plasma/MEMORY.md` for the table.

---

## What the user (Hocine) is frustrated about

He noticed in the last session that:
1. **orca-mini hallucinates current events / dates.** It's a 3B model with 2023 cutoff. This is normal but feels broken to a non-LLM-expert. The fix is Step 9 (cloud LLM escalation).
2. **Whisper mishears him.** German accent. "Moers" → "Moors", "what is today" → garbled. The fix is either `medium.en` model or eventually custom acoustic adaptation.
3. **`get_date` triggers don't include "what is today"** so simple date queries fall through to LLM. Trivial fix — extend the triggers list.

He hasn't decided what step is next: 9 (cloud LLM, recommended by me — fixes 1 above), 11 (Outlook integration), 8c (wake word), 10 (UI), or polish.

---

## Three small things you should do FIRST in your session

These are unfinished cleanup items from the chat session ending 2026-04-28:

### 1. Extend `get_date` triggers

In `backend/skills/get_date.py`, replace the `triggers` list with:

```python
"triggers": [
    "what's the date",
    "what date is it",
    "today's date",
    "what day is it",
    "what day is today",
    "what is today",
    "what is today's date",
    "tell me the date",
    "current date",
],
```

### 2. Add a `news_disclaimer` skill

Reason: the user asks about news / current events, orca-mini hallucinates badly. An honest "I can't access live news yet" skill is better than a wrong answer. File: `backend/skills/news_disclaimer.py`:

```python
"""Skill: news_disclaimer — explains Plasma can't fetch live news yet."""
from __future__ import annotations


META = {
    "name": "news_disclaimer",
    "description": "Politely declines news/current-events questions.",
    "triggers": [
        "what's the news",
        "what is the news",
        "any news",
        "news today",
        "what is happening",
        "what's happening in the world",
        "what war",
        "current events",
        "latest news",
    ],
}


def run(args=None):
    return (
        "I don't have access to live news or the internet yet. "
        "I'll get that capability when we add cloud LLM support in step 9."
    )


def self_test():
    return "live news" in run().lower()
```

### 3. Bump skill suggester confidence

The session generated a `calculator` proposal because "what is today" matched the calculator template's "what is" keyword. False positive. In `backend/modules/skills/templates.py`, change the calculator's `keywords` list from `["plus", "minus", "times", "divided", "calculate", "compute", "what is"]` to:

```python
keywords=["plus", "minus", "times", "divided", "calculate", "compute"],
```

Drop "what is" — it matches too aggressively.

After these three edits, run:

```powershell
pytest tests/ -v
```

and verify all 26 tests still pass. Then commit: