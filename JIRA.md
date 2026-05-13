# Plasma AI — Jira Sync (memory file)

**Project:** Plasma AI  **Key:** PA  **Board:** Scrum
**Timeline:** 2026-05-13 → 2026-12-15
**Hierarchy:** Epic → Story / Task / Bug → Sub-task

> RULE: Every feature shipped, bug found, or status change → update this
> file AND the Jira ticket. Source of truth between sessions.

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
| Labels | see legend |
| Start date / Due date | both required |
| Issue color | per legend |
| Linked work items | `relates to`, `blocks`, `is blocked by` |
| Flagged | `Impediment` if blocked — card turns yellow |

### Color legend (only 8 epics, color-coded)

| Color | Epic |
|---|---|
| Purple | Voice Pipeline |
| Green | Skills System |
| Yellow | Memory & User Profile |
| Blue | LLM Integration |
| Red | Wake Word |
| Orange | UI / Frontend |
| Grey-dark | Integrations |
| Grey-light | Infra / DevOps |

---

## The 8 Epics

| Key | Epic | Status | Dates |
|---|---|---|---|
| PA-1  | Voice Pipeline (mic, VAD, Whisper, Piper, multi-language) | In Progress | May 13 – Sep 16 |
| PA-13 | Skills System (registry, suggester, 20+ skills) | In Progress | May 13 – Aug 19 |
| PA-37 | Memory & User Profile (SQLite, USER.md, voice profiles) | In Progress | May 13 – Oct 15 |
| PA-46 | LLM Integration (Ollama + Groq/Claude cloud) | In Progress | May 13 – Jun 15 |
| PA-54 | Wake Word ("Hey Plasma" always-on) | To Do | Jun 10 – Jul 30 |
| PA-57 | UI / Frontend (waveform, history, mobile, analytics) | To Do | May 27 – Oct 29 |
| PA-66 | Integrations (Outlook, music, Slack, Teams) | To Do | Jul 22 – Nov 12 |
| PA-77 | Infra / DevOps (CI, packaging, installer, release) | In Progress | May 13 – Dec 15 |

---

## Full backlog — PA-1 through PA-86

---

### PA-1 — EPIC: Voice Pipeline
*Purple · label: voice · In Progress · May 13 – Sep 16*
Mic capture, VAD, Whisper ASR, Piper TTS, push-to-talk, multi-language.

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-2  | Story | Mic capture with sounddevice (int16, 16kHz) | Done | Step 5 |
| PA-3  | Story | Silero V5 VAD — voice activity detection | Done | Step 5 |
| PA-4  | Story | Whisper ASR via faster-whisper (small.en) | Done | Step 5 |
| PA-5  | Story | Piper TTS with Ryan voice — WAV output | Done | Step 6 |
| PA-6  | Story | F9 push-to-talk hotkey in browser UI | Done | Step 5 |
| PA-7  | Task  | Make Whisper model configurable via .env | Done | 648e4e7 |
| PA-8  | Story | French language support (Whisper + Piper fr voice) | To Do | — |
| PA-9  | Story | Arabic language support | To Do | — |
| PA-10 | Story | Auto language detection per utterance | To Do | — |
| PA-11 | Task  | WHISPER_LANGUAGE env var (replaces hardcoded "en") | To Do | — |
| PA-12 | Story | Multilingual skill triggers (FR / AR / EN) | To Do | — |

---

### PA-13 — EPIC: Skills System
*Green · label: skills · In Progress · May 13 – Aug 19*
Skill registry, suggester, templates, core skills + advanced + productivity skills.

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-14 | Story | Skill registry + keyword trigger routing | Done | Step 7 |
| PA-15 | Story | `get_time` skill | Done | Step 7 |
| PA-16 | Story | `get_date` skill (extended triggers) | Done | 251b8c0 |
| PA-17 | Story | `remember_this` and `forget_this` skills | Done | Step 7c |
| PA-18 | Story | `what_do_you_remember` skill | Done | Step 7c |
| PA-19 | Story | `open_app` skill (Windows) | Done | Step 7c |
| PA-20 | Story | Skill suggester — proposes skills from templates | Done | Step 8 |
| PA-21 | Story | `weather` skill via Open-Meteo API | Done | Step 8 |
| PA-22 | Story | `news_disclaimer` skill | Done | 251b8c0 |
| PA-23 | Bug   | Weather skill SSL cert error (urllib) | Done | aed8ba1 |
| PA-24 | Bug   | Calculator template false-positive on "what is" | Done | 251b8c0 |
| PA-25 | Story | Timer skill — "set a timer for 5 minutes" | To Do | — |
| PA-26 | Story | Calculator skill — math expressions by voice | To Do | — |
| PA-27 | Story | Joke skill — random joke on demand | To Do | — |
| PA-28 | Story | Unit converter — "convert 5 miles to km" | To Do | — |
| PA-29 | Story | Wikipedia lookup — "who is Einstein" | To Do | — |
| PA-30 | Story | Translation skill — "translate hello to French" | To Do | — |
| PA-31 | Story | Reminder skill — "remind me at 3pm to call Samir" | To Do | — |
| PA-32 | Story | Voice notes — "take a note: …" saves to file | To Do | — |
| PA-33 | Story | Todo list — add / read / clear by voice | To Do | — |
| PA-34 | Story | News via RSS feeds (no LLM hallucination) | To Do | — |
| PA-35 | Story | Weather forecast — 5-day, not just current | To Do | — |
| PA-36 | Story | Settings voice control — "switch to faster model" | To Do | — |

---

### PA-37 — EPIC: Memory & User Profile
*Yellow · label: memory · In Progress · May 13 – Oct 15*
SQLite store, USER.md facts, voice profiles for multi-user.

| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-38 | Story | SQLite store + FTS5 (messages + facts) | Done | Step 4 |
| PA-39 | Story | `remember_this` writes facts by voice | Done | Step 7c |
| PA-40 | Story | USER.md auto-writer (second-person rewrite) | Done | Step 8a |
| PA-41 | Story | USER.md injected into every LLM system prompt | Done | Step 8a |
| PA-42 | Story | Speaker identification (multi-user voice ID) | To Do | — |
| PA-43 | Story | Per-user memory + per-user USER.md | To Do | — |
| PA-44 | Story | Voice selection — choose TTS voice by preference | To Do | — |
| PA-45 | Story | Memory / fact browser UI (view + delete facts) | To Do | — |

---

### PA-46 — EPIC: LLM Integration
*Blue · label: llm · In Progress · May 13 – Jun 15*
Ollama local + Step 9 cloud (Groq for speed, Claude for quality).

| Key | Type | Summary | Status | Links / Commit |
|---|---|---|---|---|
| PA-47 | Story | Ollama HTTP client `/api/chat` | Done | Step 3 |
| PA-48 | Task  | Stream first sentence from Ollama (saves 3–8s) | Done | 648e4e7 |
| PA-49 | Story | **PII redaction before any cloud call** | To Do | blocks PA-50 |
| PA-50 | Story | **Cloud LLM via Groq — sub-1s replies** | To Do | blocked by PA-49 |
| PA-51 | Story | **Audit log at `.plasma/audit.log`** | To Do | relates to PA-50 |
| PA-52 | Story | **Graceful offline fallback to Ollama** | To Do | relates to PA-50 |
| PA-53 | Task  | Claude API as second cloud provider | To Do | relates to PA-50 |

---

### PA-54 — EPIC: Wake Word
*Red · label: voice · To Do · Jun 10 – Jul 30*
Always-on "Hey Plasma" detection, replaces F9.

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-55 | Story | "Hey Plasma" detection via openWakeWord | To Do |
| PA-56 | Task  | Remove F9 hotkey once wake word is stable | To Do |

---

### PA-57 — EPIC: UI / Frontend
*Orange · label: ui · To Do · May 27 – Oct 29*
Waveform, conversation history, mobile responsiveness, analytics dashboard.

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-58 | Story | Waveform visualizer while mic is active | To Do |
| PA-59 | Story | Conversation history panel (scrollable) | To Do |
| PA-60 | Story | Status indicator: idle / listening / thinking / speaking | To Do |
| PA-61 | Story | Mobile-responsive browser UI | To Do |
| PA-62 | Story | Keyboard-free mode (pure voice interaction) | To Do |
| PA-63 | Story | High-contrast / accessibility theme | To Do |
| PA-64 | Story | Skill usage stats panel (most-used skills) | To Do |
| PA-65 | Story | Response latency graph per session | To Do |

---

### PA-66 — EPIC: Integrations
*Grey-dark · label: integration · To Do · Jul 22 – Nov 12*
Outlook, music/media control, browser automation, Slack/Teams/WhatsApp.

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-67 | Story | Read today's Outlook calendar events by voice | To Do |
| PA-68 | Story | Read unread Outlook email count | To Do |
| PA-69 | Story | "Add to calendar" by voice | To Do |
| PA-70 | Story | Spotify play / pause / next / previous | To Do |
| PA-71 | Story | System volume up / down / mute | To Do |
| PA-72 | Story | Screenshot by voice — saved to Desktop | To Do |
| PA-73 | Story | "What song is playing?" via Spotify API | To Do |
| PA-74 | Story | Slack — read latest message in a channel | To Do |
| PA-75 | Story | Microsoft Teams — meeting summary by voice | To Do |
| PA-76 | Story | Send WhatsApp message by voice (via API) | To Do |

---

### PA-77 — EPIC: Infra / DevOps
*Grey-light · label: infra · In Progress · May 13 – Dec 15*
CI, tests, packaging, Windows installer, release v1.0.

| Key | Type | Summary | Status |
|---|---|---|---|
| PA-78 | Task  | pytest CI on every push (GitHub Actions) | To Do |
| PA-79 | Task  | Windows installer via PyInstaller | To Do |
| PA-80 | Task  | `.env.example` always up to date | Done |
| PA-81 | Task  | Auto-update mechanism (check GitHub releases) | To Do |
| PA-82 | Story | First-run setup wizard (mic test, model download) | To Do |
| PA-83 | Task  | Public documentation site (GitHub Pages) | To Do |
| PA-84 | Task  | Conventional commits enforcement + changelog gen | To Do |
| PA-85 | Task  | v1.0.0 release tag + changelog | To Do |
| PA-86 | Task  | Demo video for README | To Do |

---

## Sprint plan (May 13 → Dec 15, 2026)

| Sprint | Dates | Goal | Tickets |
|---|---|---|---|
| **S1** | May 13 – May 27 | Cloud LLM | PA-49, 50, 51, 52 |
| S2  | May 27 – Jun 10 | UI essentials | PA-58, 59, 60 |
| S3  | Jun 10 – Jun 24 | Wake word | PA-55, 56 |
| S4  | Jun 24 – Jul 8  | Skills batch 1 | PA-25, 26, 27, 28 |
| S5  | Jul 8 – Jul 22  | Skills batch 2 | PA-29, 30, 31 |
| S6  | Jul 22 – Aug 5  | Outlook | PA-67, 68, 69 |
| S7  | Aug 5 – Aug 19  | Productivity skills | PA-32, 33, 34, 35 |
| S8  | Aug 19 – Sep 2  | Music & media | PA-70, 71, 72, 73 |
| S9  | Sep 2 – Sep 16  | Multi-language | PA-8, 9, 10, 11, 12 |
| S10 | Sep 16 – Sep 30 | Mobile UI | PA-61, 62, 63 |
| S11 | Oct 1 – Oct 15  | Voice profiles | PA-42, 43, 44 |
| S12 | Oct 15 – Oct 29 | Analytics | PA-64, 65, 45 |
| S13 | Oct 29 – Nov 12 | Slack / Teams / WhatsApp | PA-74, 75, 76 |
| S14 | Nov 12 – Nov 26 | Packaging & CI | PA-78, 79, 82 |
| S15 | Nov 26 – Dec 10 | Auto-update & docs | PA-81, 83, 84, 36 |
| S16 | Dec 10 – Dec 15 | v1.0 release | PA-53, 85, 86 |

---

## Active sprint — S1 (May 13 – May 27)

| Ticket | Summary | Status |
|---|---|---|
| PA-49 | PII redaction before cloud call | To Do |
| PA-50 | Cloud LLM via Groq | To Do |
| PA-51 | Audit log | To Do |
| PA-52 | Offline fallback to Ollama | To Do |

---

## Commit convention

```
PA-50: add Groq client with streaming first-sentence
PA-23: fix weather SSL cert error
```

GitHub auto-links commits to tickets once **Project Settings → Integrations → GitHub** is connected.

---

## Workflow rules

- **Bug found** → create Bug under its epic, link `is blocked by` if it stops a story, flag `Impediment` if it blocks the sprint
- **Feature done** → move to Done, paste commit hash in description, update this file
- **Sprint planning** → Mondays — pull top 3-5 stories into active sprint
- **Daily** → mark one in-progress ticket, flag impediments, no work without a ticket
- **Session end** → this file must reflect reality before closing
