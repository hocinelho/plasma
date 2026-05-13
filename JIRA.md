# Plasma AI — Jira Sync (memory file)

**Project:** Plasma AI
**Key:** PA
**Board:** Scrum
**Hierarchy:** Epic → Story / Task / Bug → Sub-task

> RULE: Whenever a feature ships, a bug appears, or a story changes status,
> update this file **and** the matching Jira ticket. This file is the source
> of truth between Claude sessions.

---

## Issue types

| Type | When to use |
|---|---|
| **Epic** | A big feature area. Spans many sprints. |
| **Story** | A user-facing capability that fits one sprint. |
| **Task** | Technical work without direct user value. |
| **Bug** | A defect in something that already works. |
| **Sub-task** | Breakdown of a parent Story/Task. Use sparingly. |

## Required fields on every Epic

| Field | Why |
|---|---|
| Summary | Short title — `EPIC: Voice Pipeline` |
| Description | What it delivers + done criteria |
| Status | To Do / In Progress / Done |
| Labels | `voice`, `llm`, `skills`, `ui`, `infra`, `integration`, `memory` |
| Start date / Due date | Always set both |
| Issue color | Per legend below |
| Linked work items | `relates to`, `blocks`, `is blocked by`, `duplicates` |
| Flagged | Set to `Impediment` if blocked (card turns yellow) |

### Color legend

| Color | Area |
|---|---|
| Purple | Voice pipeline / wake word |
| Blue | LLM integration |
| Green | Skills system |
| Yellow | Memory / USER.md |
| Orange | UI / frontend |
| Red | Hotfix bug epic |
| Grey | Infra / integrations |

---

## Full backlog — sequential PA-1 through PA-47

### PA-1 — EPIC: Voice Pipeline   *(Purple, label: voice, In Progress)*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-2 | Story | Mic capture with sounddevice (int16, 16kHz) | Done | Step 5 |
| PA-3 | Story | Silero V5 VAD — voice activity detection | Done | Step 5 |
| PA-4 | Story | Whisper ASR via faster-whisper (small.en) | Done | Step 5 |
| PA-5 | Story | Piper TTS with Ryan voice — WAV output | Done | Step 6 |
| PA-6 | Story | F9 push-to-talk hotkey in browser UI | Done | Step 5 |
| PA-7 | Task  | Make Whisper model configurable via `.env` | Done | 648e4e7 |

### PA-8 — EPIC: Skills System   *(Green, label: skills, In Progress)*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-9  | Story | Skill registry + keyword trigger routing | Done | Step 7 |
| PA-10 | Story | `get_time` skill | Done | Step 7 |
| PA-11 | Story | `get_date` skill (extended triggers) | Done | Step 7c / 251b8c0 |
| PA-12 | Story | `remember_this` and `forget_this` skills | Done | Step 7c / Step 8a |
| PA-13 | Story | `what_do_you_remember` skill | Done | Step 7c |
| PA-14 | Story | `open_app` skill (Windows) | Done | Step 7c |
| PA-15 | Story | Skill suggester — proposes skills from templates | Done | Step 8 |
| PA-16 | Story | `weather` skill via Open-Meteo API | Done | Step 8 |
| PA-17 | Story | `news_disclaimer` skill — honest "no live news yet" | Done | 251b8c0 |
| PA-18 | Bug   | Weather skill SSL cert error — urllib missing CA | Done | aed8ba1 |
| PA-19 | Bug   | Calculator template false-positive on "what is" | Done | 251b8c0 |

### PA-20 — EPIC: Memory & User Profile   *(Yellow, label: memory, Done)*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-21 | Story | SQLite memory store with FTS5 (messages + facts) | Done | Step 4 |
| PA-22 | Story | `remember_this` writes facts via voice | Done | Step 7c |
| PA-23 | Story | USER.md auto-writer — second-person rewrite of facts | Done | Step 8a |
| PA-24 | Story | USER.md injected into every LLM system prompt | Done | Step 8a |

### PA-25 — EPIC: LLM Integration   *(Blue, label: llm, In Progress)*

| Key | Type | Summary | Status | Links / Commit |
|---|---|---|---|---|
| PA-26 | Story | Ollama HTTP client `/api/chat` | Done | Step 3 |
| PA-27 | Task  | Stream first sentence from Ollama (saves 3–8s) | Done | 648e4e7 |
| PA-28 | Story | **PII redaction before any cloud call** | To Do | blocks PA-29 |
| PA-29 | Story | **Cloud LLM via Groq — sub-1s replies** | To Do | is blocked by PA-28 |
| PA-30 | Story | **Audit log at `.plasma/audit.log`** | To Do | relates to PA-29 |
| PA-31 | Story | **Graceful offline fallback to Ollama** | To Do | relates to PA-29 |
| PA-32 | Task  | Claude API client as second cloud provider | To Do | relates to PA-29 |

### PA-33 — EPIC: Wake Word   *(Purple, label: voice, To Do)*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-34 | Story | "Hey Plasma" detection via openWakeWord | To Do |
| PA-35 | Task  | Remove F9 hotkey once wake word is stable | To Do |

### PA-36 — EPIC: UI / Frontend   *(Orange, label: ui, To Do)*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-37 | Story | Waveform visualizer while mic is active | To Do |
| PA-38 | Story | Conversation history panel (scrollable) | To Do |
| PA-39 | Story | Status indicator: idle / listening / thinking / speaking | To Do |

### PA-40 — EPIC: Integrations   *(Grey, label: integration, To Do)*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-41 | Story | Read today's Outlook calendar events by voice | To Do |
| PA-42 | Story | Read unread Outlook email count | To Do |
| PA-43 | Story | "Add to calendar" by voice | To Do |

### PA-44 — EPIC: Infra / DevOps   *(Grey, label: infra, In Progress)*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-45 | Task  | `pytest tests/ -v` runs on every push (GitHub Actions) | To Do |
| PA-46 | Task  | Windows installer via PyInstaller | To Do |
| PA-47 | Task  | `.env.example` always up to date | Done |

---

## Active sprint

**Sprint 1 — Cloud LLM (2 weeks)**

In sprint:
- PA-28 PII redaction (must finish first — blocks PA-29)
- PA-29 Cloud LLM via Groq
- PA-30 Audit log
- PA-31 Offline fallback

Target velocity: ~13 story points.

---

## Commit ↔ Jira convention

Commit messages start with the Jira key:

```
PA-29: add Groq client with streaming
PA-18: fix weather skill SSL cert error
```

After Project Settings → Integrations → GitHub is connected,
Jira auto-links commits to tickets.

---

## Workflow rules

- **Bug found** → create a `Bug` under its epic, link `is blocked by` if it stops a story, flag as `Impediment` if it blocks the sprint.
- **Feature done** → move story to Done, paste commit hash in description, update this file.
- **Sprint planning** → every Monday pull top 3-5 stories into the active sprint.
- **Daily** → mark in-progress, flag impediments, no work without a ticket.
