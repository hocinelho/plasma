# Plasma AI — Jira Sync (memory file)

**Project:** Plasma AI
**Key:** PA
**Board:** Scrum
**Hierarchy:** Epic → Story / Task / Bug → Sub-task

> RULE: Whenever a feature ships, a bug appears, or a story changes status,
> update this file **and** the matching Jira ticket. This file is the source
> of truth between Claude sessions.

---

## Issue types we use

| Type | When to use |
|---|---|
| **Epic** | A big feature area (e.g. "Voice Pipeline", "LLM Integration"). Spans many sprints. |
| **Story** | A user-facing capability that fits in one sprint. "As a user, I want…" |
| **Task** | Technical work without direct user value (refactor, infra, CI). |
| **Bug** | A defect in something that already works. |
| **Sub-task** | A breakdown of a parent Story/Task. Use sparingly. |

---

## Required Epic fields (we always fill these)

| Field | Why |
|---|---|
| **Summary** | Short title — `EPIC: Voice Pipeline` |
| **Description** | What this epic delivers + done criteria |
| **Status** | To Do / In Progress / Done |
| **Labels** | `voice`, `llm`, `skills`, `ui`, `infra`, `integration` |
| **Start date** | When work begins |
| **Due date** | Target completion |
| **Issue color** | Color-coded per area (see legend below) |
| **Linked work items** | `relates to`, `blocks`, `is blocked by`, `duplicates` |
| **Flagged** | Set to `Impediment` if blocked (turns card yellow) |

### Color legend (set per epic in Jira)

| Color | Area |
|---|---|
| Purple | Voice pipeline (mic / ASR / TTS) |
| Blue | LLM integration (Ollama / cloud) |
| Green | Skills system |
| Yellow | Memory / USER.md |
| Orange | UI / frontend |
| Red | Bugs hotfix epic |
| Grey | Infra / DevOps |

---

## Epics — current state

| Key | Summary | Status | Color | Labels |
|---|---|---|---|---|
| PA-1 | EPIC: Voice Pipeline | In Progress | Purple | `voice` |
| PA-2 | EPIC: Skills System | In Progress | Green | `skills` |
| PA-3 | EPIC: Memory & USER Profile | Done | Yellow | `memory` |
| PA-4 | EPIC: LLM Integration | To Do | Blue | `llm` |
| PA-5 | EPIC: Wake Word | To Do | Purple | `voice` |
| PA-6 | EPIC: UI / Frontend | To Do | Orange | `ui` |
| PA-7 | EPIC: Integrations (Outlook etc.) | To Do | Grey | `integration` |
| PA-8 | EPIC: Infra / DevOps | In Progress | Grey | `infra` |

---

## Stories & tasks — current state

### Under PA-1 (Voice Pipeline)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-10 | Story | Mic capture with sounddevice | Done | Step 5 |
| PA-11 | Story | Silero V5 VAD | Done | Step 5 |
| PA-12 | Story | Whisper ASR via faster-whisper | Done | Step 5 |
| PA-13 | Story | Piper TTS with Ryan voice | Done | Step 6 |
| PA-14 | Task | Make Whisper model configurable via `.env` | Done | 648e4e7 |
| PA-15 | Story | F9 push-to-talk hotkey | Done | Step 5 |

### Under PA-2 (Skills System)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-20 | Story | Skill registry + trigger routing | Done | Step 7 |
| PA-21 | Story | `get_time` skill | Done | Step 7 |
| PA-22 | Story | `get_date` skill | Done | Step 7c |
| PA-23 | Story | `remember_this` / `forget_this` skills | Done | Step 7c |
| PA-24 | Story | `open_app` skill | Done | Step 7c |
| PA-25 | Story | Skill suggester (template-based proposals) | Done | Step 8 |
| PA-26 | Story | `weather` skill (Open-Meteo) | Done | Step 8 |
| PA-27 | Story | `news_disclaimer` skill | Done | Polish 8 |
| PA-28 | Bug  | weather skill SSL cert error (urllib) | Done | aed8ba1 |
| PA-29 | Bug  | calculator template false-positive on "what is" | Done | 251b8c0 |

### Under PA-3 (Memory)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-30 | Story | SQLite memory store + FTS5 | Done | Step 4 |
| PA-31 | Story | USER.md auto-writer (2nd-person rewrite) | Done | Step 8a |

### Under PA-4 (LLM Integration) — NEXT SPRINT
| Key | Type | Summary | Status | Notes |
|---|---|---|---|---|
| PA-40 | Story | Ollama HTTP client (`/api/chat`) | Done | Step 3 |
| PA-41 | Task | Stream first sentence from Ollama | Done | 648e4e7 |
| PA-42 | Story | **Cloud LLM via Groq (sub-1s replies)** | To Do | Step 9 |
| PA-43 | Story | **PII redaction before any cloud call** | To Do | blocks PA-42 |
| PA-44 | Story | **Audit log at `.plasma/audit.log`** | To Do | Step 9 |
| PA-45 | Story | **Graceful offline fallback to Ollama** | To Do | Step 9 |
| PA-46 | Task | Claude API client as second cloud provider | To Do | Step 9b |

### Under PA-5 (Wake Word)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-50 | Story | "Hey Plasma" detection (openWakeWord) | To Do |

### Under PA-6 (UI)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-60 | Story | Waveform visualizer while listening | To Do |
| PA-61 | Story | Conversation history panel | To Do |

### Under PA-7 (Integrations)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-70 | Story | Outlook calendar — today's events | To Do |
| PA-71 | Story | Outlook unread email count | To Do |

### Under PA-8 (Infra)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-80 | Task | `pytest tests/ -v` in CI on every push | To Do |
| PA-81 | Task | Windows installer (PyInstaller) | To Do |

---

## Active sprint

**Sprint 1 — Cloud LLM (2 weeks)**

In sprint:
- PA-42 Cloud LLM via Groq
- PA-43 PII redaction
- PA-44 Audit log
- PA-45 Offline fallback

Velocity target: ~13 story points.

---

## How commits link to Jira

Every commit message must start with the Jira key:

```
PA-42: add Groq client with streaming
```

Once GitHub is connected (Project Settings → Integrations → GitHub),
commits and PRs auto-update the linked ticket.

---

## Workflow rules

- **Bug found:** create a `Bug` under the relevant epic, link with `is blocked by` if it stops a story, flag as `Impediment` if it blocks the sprint.
- **Feature done:** move story to Done, add the commit hash in the description, update this file.
- **Sprint planning:** every Monday — pull the top 3-5 stories from backlog into the active sprint.
- **Daily:** mark in-progress story, flag impediments, no work without a ticket.
