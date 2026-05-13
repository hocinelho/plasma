# Plasma AI — Jira Sync (memory file)

**Project:** Plasma AI  **Key:** PA  **Board:** Scrum
**Timeline:** 2026-05-13 → 2026-12-15
**Hierarchy:** Epic → Story / Task / Bug → Sub-task

> RULE: Every feature shipped, bug found, or status change → update this
> file AND the Jira ticket. This is the source of truth between sessions.

---

## Issue types

| Type | When to use |
|---|---|
| **Epic** | Big feature area, spans many sprints |
| **Story** | User-facing capability, fits one sprint |
| **Task** | Technical work, no direct user value |
| **Bug** | Defect in something that already works |
| **Sub-task** | Breakdown of a parent issue, use sparingly |

## Required fields on every Epic

| Field | Rule |
|---|---|
| Summary | `EPIC: <name>` |
| Description | What it delivers + done criteria |
| Status | To Do / In Progress / Done |
| Labels | see color legend |
| Start date | per sprint plan below |
| Due date | per sprint plan below |
| Issue color | per legend |
| Linked work items | `relates to`, `blocks`, `is blocked by` |
| Flagged | `Impediment` if blocked — card turns yellow |

### Color legend

| Color | Area |
|---|---|
| Purple | Voice pipeline / wake word / multi-language |
| Blue | LLM integration |
| Green | Skills system / advanced skills |
| Yellow | Memory / productivity |
| Orange | UI / mobile |
| Grey | Infra / integrations / release |
| Red | Hotfix bug epics |

---

## Sprint plan (May 13 → Dec 15, 2026)

| Sprint | Dates | Goal | Key tickets |
|---|---|---|---|
| S1 | May 13 – May 27 | Cloud LLM | PA-28, 29, 30, 31 |
| S2 | May 27 – Jun 10 | UI + Wake word prep | PA-37, 38, 39 |
| S3 | Jun 10 – Jun 24 | Wake word | PA-34, 35 |
| S4 | Jun 24 – Jul 8 | Advanced skills batch 1 | PA-49, 50, 51, 52 |
| S5 | Jul 8 – Jul 22 | Advanced skills batch 2 | PA-53, 54, 55 |
| S6 | Jul 22 – Aug 5 | Outlook integration | PA-41, 42, 43 |
| S7 | Aug 5 – Aug 19 | Productivity skills | PA-67, 68, 69, 70 |
| S8 | Aug 19 – Sep 2 | Music & media | PA-63, 64, 65, 66 |
| S9 | Sep 2 – Sep 16 | Multi-language | PA-58, 59, 60, 61 |
| S10 | Sep 16 – Sep 30 | Mobile UI | PA-76, 77, 78 |
| S11 | Oct 1 – Oct 15 | Voice profiles | PA-72, 73, 74 |
| S12 | Oct 15 – Oct 29 | Analytics dashboard | PA-80, 81, 82 |
| S13 | Oct 29 – Nov 12 | Slack / Teams | PA-84, 85, 86 |
| S14 | Nov 12 – Nov 26 | Packaging & CI | PA-45, 46, 88, 89 |
| S15 | Nov 26 – Dec 10 | Setup wizard + docs | PA-90, 91, 92 |
| S16 | Dec 10 – Dec 15 | Release polish | PA-93, 94 |

---

## Full backlog — PA-1 through PA-94

---

### PA-1 — EPIC: Voice Pipeline
*Purple · label: voice · In Progress · May 13 – Jun 30*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-2 | Story | Mic capture with sounddevice (int16, 16kHz) | Done | Step 5 |
| PA-3 | Story | Silero V5 VAD — voice activity detection | Done | Step 5 |
| PA-4 | Story | Whisper ASR via faster-whisper (small.en) | Done | Step 5 |
| PA-5 | Story | Piper TTS with Ryan voice — WAV output | Done | Step 6 |
| PA-6 | Story | F9 push-to-talk hotkey in browser UI | Done | Step 5 |
| PA-7 | Task  | Make Whisper model configurable via .env | Done | 648e4e7 |

---

### PA-8 — EPIC: Skills System
*Green · label: skills · In Progress · May 13 – Jul 15*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-9  | Story | Skill registry + keyword trigger routing | Done | Step 7 |
| PA-10 | Story | `get_time` skill | Done | Step 7 |
| PA-11 | Story | `get_date` skill (extended triggers) | Done | 251b8c0 |
| PA-12 | Story | `remember_this` and `forget_this` skills | Done | Step 7c |
| PA-13 | Story | `what_do_you_remember` skill | Done | Step 7c |
| PA-14 | Story | `open_app` skill (Windows) | Done | Step 7c |
| PA-15 | Story | Skill suggester — proposes skills from templates | Done | Step 8 |
| PA-16 | Story | `weather` skill via Open-Meteo API | Done | Step 8 |
| PA-17 | Story | `news_disclaimer` skill — no live news | Done | 251b8c0 |
| PA-18 | Bug   | Weather skill SSL cert error (urllib) | Done | aed8ba1 |
| PA-19 | Bug   | Calculator template false-positive "what is" | Done | 251b8c0 |

---

### PA-20 — EPIC: Memory & User Profile
*Yellow · label: memory · Done*

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-21 | Story | SQLite store + FTS5 (messages + facts) | Done | Step 4 |
| PA-22 | Story | `remember_this` writes facts by voice | Done | Step 7c |
| PA-23 | Story | USER.md auto-writer (second-person rewrite) | Done | Step 8a |
| PA-24 | Story | USER.md injected into every LLM system prompt | Done | Step 8a |

---

### PA-25 — EPIC: LLM Integration
*Blue · label: llm · In Progress · May 13 – Jun 15*

| Key | Type | Summary | Status | Links |
|---|---|---|---|---|
| PA-26 | Story | Ollama HTTP client `/api/chat` | Done | — |
| PA-27 | Task  | Stream first sentence from Ollama (saves 3–8s) | Done | 648e4e7 |
| PA-28 | Story | **PII redaction before any cloud call** | To Do | blocks PA-29 |
| PA-29 | Story | **Cloud LLM via Groq — sub-1s replies** | To Do | blocked by PA-28 |
| PA-30 | Story | **Audit log at .plasma/audit.log** | To Do | relates to PA-29 |
| PA-31 | Story | **Graceful offline fallback to Ollama** | To Do | relates to PA-29 |
| PA-32 | Task  | Claude API as second cloud provider | To Do | relates to PA-29 |

---

### PA-33 — EPIC: Wake Word
*Purple · label: voice · To Do · Jun 10 – Jul 30*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-34 | Story | "Hey Plasma" detection via openWakeWord | To Do |
| PA-35 | Task  | Remove F9 hotkey once wake word is stable | To Do |

---

### PA-36 — EPIC: UI / Frontend
*Orange · label: ui · To Do · May 27 – Aug 1*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-37 | Story | Waveform visualizer while mic is active | To Do |
| PA-38 | Story | Conversation history panel (scrollable) | To Do |
| PA-39 | Story | Status indicator: idle / listening / thinking / speaking | To Do |

---

### PA-40 — EPIC: Outlook Integration
*Grey · label: integration · To Do · Jul 22 – Sep 1*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-41 | Story | Read today's Outlook calendar events by voice | To Do |
| PA-42 | Story | Read unread Outlook email count | To Do |
| PA-43 | Story | "Add to calendar" by voice | To Do |

---

### PA-44 — EPIC: Infra / DevOps
*Grey · label: infra · In Progress · May 13 – Dec 15*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-45 | Task  | pytest CI on every push (GitHub Actions) | To Do |
| PA-46 | Task  | Windows installer via PyInstaller | To Do |
| PA-47 | Task  | `.env.example` always up to date | Done |

---

### PA-48 — EPIC: Advanced Skills
*Green · label: skills · To Do · Jun 24 – Aug 5*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-49 | Story | Timer skill — "set a timer for 5 minutes" | To Do |
| PA-50 | Story | Calculator skill — math expressions by voice | To Do |
| PA-51 | Story | Joke skill — random joke on demand | To Do |
| PA-52 | Story | Unit converter — "convert 5 miles to km" | To Do |
| PA-53 | Story | Wikipedia lookup — "who is Einstein" | To Do |
| PA-54 | Story | Translation skill — "translate hello to French" | To Do |
| PA-55 | Story | Reminder skill — "remind me at 3pm to call Samir" | To Do |

---

### PA-56 — EPIC: Multi-language Support
*Purple · label: voice · To Do · Sep 2 – Oct 15*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-57 | Story | French language support (Whisper + Piper fr voice) | To Do |
| PA-58 | Story | Arabic language support | To Do |
| PA-59 | Story | Auto language detection per utterance | To Do |
| PA-60 | Story | Multilingual skill triggers (FR/AR/EN) | To Do |
| PA-61 | Task  | WHISPER_LANGUAGE env var (replaces hardcoded "en") | To Do |

---

### PA-62 — EPIC: Music & Media Control
*Grey · label: integration · To Do · Aug 5 – Sep 2*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-63 | Story | Spotify play / pause / next / previous by voice | To Do |
| PA-64 | Story | System volume up/down/mute by voice | To Do |
| PA-65 | Story | Screenshot by voice — saved to Desktop | To Do |
| PA-66 | Story | "What song is playing?" via Spotify API | To Do |

---

### PA-67 — EPIC: Productivity Skills
*Yellow · label: skills · To Do · Aug 5 – Sep 16*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-68 | Story | Voice notes — "take a note: …" → saves to file | To Do |
| PA-69 | Story | Todo list — add / read / clear by voice | To Do |
| PA-70 | Story | News via RSS feeds (no hallucination) | To Do |
| PA-71 | Story | Weather forecast — 5-day, not just current | To Do |

---

### PA-72 — EPIC: Voice Profiles
*Purple · label: voice · To Do · Oct 1 – Nov 12*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-73 | Story | Speaker identification (multi-user) | To Do |
| PA-74 | Story | Per-user memory and USER.md | To Do |
| PA-75 | Story | Voice selection — choose TTS voice by preference | To Do |

---

### PA-76 — EPIC: Mobile & Accessibility
*Orange · label: ui · To Do · Sep 16 – Oct 31*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-77 | Story | Mobile-responsive browser UI | To Do |
| PA-78 | Story | Keyboard-free mode (pure voice interaction) | To Do |
| PA-79 | Story | High-contrast / accessibility theme | To Do |

---

### PA-80 — EPIC: Analytics & Dashboard
*Grey · label: infra · To Do · Oct 1 – Nov 12*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-81 | Story | Skill usage stats panel (most-used skills) | To Do |
| PA-82 | Story | Response latency graph per session | To Do |
| PA-83 | Story | Memory / fact browser UI (view + delete facts) | To Do |

---

### PA-84 — EPIC: Communication Integrations
*Grey · label: integration · To Do · Oct 15 – Nov 26*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-85 | Story | Slack — read latest message in a channel | To Do |
| PA-86 | Story | Microsoft Teams — meeting summary by voice | To Do |
| PA-87 | Story | Send WhatsApp message by voice (via API) | To Do |

---

### PA-88 — EPIC: Release & Distribution
*Grey · label: infra · To Do · Nov 12 – Dec 15*

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-89 | Task  | Auto-update mechanism (check GitHub releases) | To Do |
| PA-90 | Story | First-run setup wizard (mic test, model download) | To Do |
| PA-91 | Task  | Public documentation site (GitHub Pages) | To Do |
| PA-92 | Story | Settings voice control ("switch to faster model") | To Do |
| PA-93 | Task  | v1.0.0 release tag + changelog | To Do |
| PA-94 | Task  | Demo video for README | To Do |

---

## Active sprint — S1 (May 13 – May 27)

| Ticket | Summary | Status |
|---|---|---|
| PA-28 | PII redaction before cloud call | To Do |
| PA-29 | Cloud LLM via Groq | To Do |
| PA-30 | Audit log | To Do |
| PA-31 | Offline fallback to Ollama | To Do |

---

## Commit convention

```
PA-29: add Groq client with streaming first-sentence
PA-18: fix weather SSL cert error
```

GitHub auto-links commits to tickets once Project Settings → Integrations → GitHub is connected.

---

## Workflow rules

- **Bug found** → create Bug under its epic, link `is blocked by` if it stops a story, flag `Impediment` if it blocks the sprint
- **Feature done** → move to Done, paste commit hash in description, update this file
- **Sprint planning** → Mondays — pull top 3-5 stories into active sprint
- **Daily** → mark one in-progress ticket, flag impediments, no work without a ticket
- **Session end** → this file must reflect reality before closing
