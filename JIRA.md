# Plasma AI — Jira Sync (memory file)

**Project:** Plasma AI  **Key:** PA  **Board:** Scrum
**Timeline:** 2026-05-13 → 2026-12-15

> RULE: Every feature shipped, bug found, or status change → update this
> file AND the Jira ticket. Source of truth between sessions.

---

## The 8 Epics (already in Jira)

| Key | Epic | Color | Status | Dates |
|---|---|---|---|---|
| PA-1  | EPIC: Voice Pipeline | Purple | In Progress | May 13 – Sep 16 |
| PA-8  | EPIC: Skills System | Green | In Progress | May 13 – Aug 19 |
| PA-20 | EPIC: Memory & User Profile | Yellow | In Progress | May 13 – Oct 15 |
| PA-25 | EPIC: LLM Integration | Blue | In Progress | May 13 – Jun 15 |
| PA-33 | EPIC: Wake Word | Red | To Do | Jun 10 – Jul 30 |
| PA-36 | EPIC: UI / Frontend | Orange | To Do | May 27 – Oct 29 |
| PA-40 | EPIC: Integrations | Grey-dark | To Do | Jul 22 – Nov 12 |
| PA-44 | EPIC: Infra / DevOps | Grey-light | In Progress | May 13 – Dec 15 |

---

## PA-1 through PA-47 — already created in Jira

### PA-1 — EPIC: Voice Pipeline (children PA-2 → PA-7)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-2 | Story | Mic capture with sounddevice (int16, 16kHz) | Done | Step 5 |
| PA-3 | Story | Silero V5 VAD — voice activity detection | Done | Step 5 |
| PA-4 | Story | Whisper ASR via faster-whisper (small.en) | Done | Step 5 |
| PA-5 | Story | Piper TTS with Ryan voice — WAV output | Done | Step 6 |
| PA-6 | Story | F9 push-to-talk hotkey in browser UI | Done | Step 5 |
| PA-7 | Task  | Make Whisper model configurable via .env | Done | 648e4e7 |

### PA-8 — EPIC: Skills System (children PA-9 → PA-19)
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
| PA-17 | Story | `news_disclaimer` skill | Done | 251b8c0 |
| PA-18 | Bug   | Weather skill SSL cert error (urllib) | Done | aed8ba1 |
| PA-19 | Bug   | Calculator template false-positive on "what is" | Done | 251b8c0 |

### PA-20 — EPIC: Memory & User Profile (children PA-21 → PA-24)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-21 | Story | SQLite store + FTS5 (messages + facts) | Done | Step 4 |
| PA-22 | Story | `remember_this` writes facts by voice | Done | Step 7c |
| PA-23 | Story | USER.md auto-writer (second-person rewrite) | Done | Step 8a |
| PA-24 | Story | USER.md injected into every LLM system prompt | Done | Step 8a |

### PA-25 — EPIC: LLM Integration (children PA-26 → PA-32)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-26 | Story | Ollama HTTP client `/api/chat` | Done | Step 3 |
| PA-27 | Task  | Stream first sentence from Ollama (saves 3–8s) | Done | 648e4e7 |
| PA-28 | Story | PII redaction before any cloud call | **Done** | a5150a2 |
| PA-29 | Story | Cloud LLM via Groq — sub-1s replies | **Done** | 45f7346 |
| PA-29.1 | Task | Refactor cloud client to provider-agnostic CLOUD_* vars (Gemini default) | **Done** | f916ad7 |
| PA-30 | Story | Audit log at `.plasma/audit.log` | **Done** | 23b4ac2 |
| PA-31 | Story | Graceful offline fallback to Ollama | **Done** | built into chat_service |
| PA-32 | Task  | Claude API as second cloud provider | To Do | — |

### PA-33 — EPIC: Wake Word (children PA-34 → PA-35)
| Key | Type | Summary | Status | Commit |
|---|---|---|---|---|
| PA-34 | Story | "Hey Plasma" detection via openWakeWord | **Done** | 702c905 |
| PA-35 | Task  | Remove F9 hotkey once wake word is stable | **Done** | 7ef9668+ |

### PA-36 — EPIC: UI / Frontend (children PA-37 → PA-39)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-37 | Story | Waveform visualizer while mic is active | **Done** | 926b127 |
| PA-38 | Story | Conversation history panel (scrollable) | **Done** | 926b127 |
| PA-39 | Story | Status indicator: idle / listening / thinking / speaking | **Done** | 926b127 |

### PA-40 — EPIC: Integrations (children PA-41 → PA-43)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-41 | Story | Read today's Outlook calendar events by voice | **Done** |
| PA-42 | Story | Read unread Outlook email count | **Done** |
| PA-43 | Story | "Add to calendar" by voice | **Done** |

### PA-44 — EPIC: Infra / DevOps (children PA-45 → PA-47)
| Key | Type | Summary | Status |
|---|---|---|---|
| PA-45 | Task  | pytest CI on every push (GitHub Actions) | **Done** |
| PA-46 | Task  | Windows installer via PyInstaller | **Done** |
| PA-47 | Task  | `.env.example` always up to date | Done |
| PA-87 | Bug   | Corporate-proxy TLS: CERTIFICATE_VERIFY_FAILED on Wikipedia/translator/weather | **Done** | b8b4901 |
| PA-88 | Bug   | Weather routed to calculator — "what is " trigger outranked "weather" | **Done** | 601d78b |

**PA-87 fix:** `backend/core/http_client.py` builds a `truststore.SSLContext` that
delegates verification to the Windows cert store (handles corporate MITM CAs).
`PLASMA_INSECURE_SSL=true` escape hatch for trusted local networks.
**PA-88 fix:** added longer explicit weather triggers ("what is the weather", etc.)
so longest-trigger-wins router picks weather over calculator.

---

## PA-48 through PA-92 — ADD THESE NOW (new features)

### Add to PA-1 (Voice Pipeline) — multi-language

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-48 | Story | German language support (Whisper small + Piper de_DE-thorsten) | S9 | **Done** |
| PA-49 | Story | Arabic language support | Backlog | To Do |
| PA-50 | Story | Auto language detection per utterance | S9 | **Done** |
| PA-51 | Task  | WHISPER_LANGUAGE env var | S9 | **Done** |
| PA-52 | Story | Multilingual skill triggers (DE / EN) | S9 | **Done** |

**S9 notes:**
- User said "gremany not frensh and english first" → German + English only (not French/Arabic).
- `WHISPER_LANGUAGE=auto` passes `language=None` to faster-whisper for auto-detect; requires `WHISPER_MODEL=small` (multilingual).
- English-only `.en` models warn and force `lang="en"` when auto is requested.
- German voice: run `python scripts/download_de_voice.py` then set `TTS_VOICE_DE=voices/de_DE-thorsten-medium.onnx`.
- Skills updated with German triggers + bilingual responses: get_time, get_date, joke, timer, calculator, weather.
- Language flows: ASR → `asr_result["language"]` → `handle_chat(language=)` → `skill.invoke(args["language"])` → `tts_synthesize(language=)`.

### Add to PA-8 (Skills System) — advanced + productivity skills

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-53 | Story | Timer skill — "set a timer for 5 minutes" | S4 | **Done** |
| PA-54 | Story | Calculator skill — math by voice | S4 | **Done** |
| PA-55 | Story | Joke skill — random joke on demand | S4 | **Done** |
| PA-56 | Story | Unit converter — "convert 5 miles to km" | S4 | **Done** |
| PA-57 | Story | Wikipedia lookup — "who is Einstein" | S5 | **Done** |
| PA-58 | Story | Translation skill — "say hello in French" | S5 | **Done** |
| PA-59 | Story | Reminder skill — "remind me at 3pm" | S5 | **Done** |
| PA-60 | Story | Voice notes — "take a note: …" | S7 | **Done** |
| PA-61 | Story | Todo list — add / read / clear by voice | S7 | **Done** |
| PA-62 | Story | News via RSS feeds (no LLM hallucination) | S7 | **Done** |
| PA-63 | Story | Weather forecast — 5-day not just current | S7 | **Done** |
| PA-64 | Story | Settings control — "switch to faster model" | S15 | **Done** |

### Add to PA-20 (Memory) — voice profiles

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-65 | Story | Speaker identification (multi-user) | S11 | **Done** |
| PA-66 | Story | Per-user memory + per-user USER.md | S11 | **Done** |
| PA-67 | Story | Voice selection — choose TTS voice | S11 | **Done** |
| PA-68 | Story | Memory / fact browser UI | S12 | **Done** |

**S11 notes:**
- PA-65: `backend/modules/voice/speaker_id.py` — resemblyzer embeddings (OPTIONAL dep,
  `pip install resemblyzer`), profiles in `.plasma/speakers.json`, cosine match vs
  `SPEAKER_THRESHOLD` (default 0.70). Enroll by voice: "remember my voice as <name>"
  (DE: "merke dir meine stimme als <name>") — intercepted in main.py before skill
  routing because it needs raw audio. Gracefully disabled when lib missing.
- PA-66: `facts` table gained nullable `user` column (auto-migration); `get_facts(user=X)`
  returns personal + shared (NULL) facts; per-user `USER_<Name>.md`; system prompt says
  "You are currently talking to <name>" and loads their profile. remember_this scopes
  facts to the identified speaker.
- PA-67: `voice_select` skill — "switch voice to thorsten", "list voices", "reset voice";
  `tts.set_voice_override()` wins over default + German voice until reset.
- New `who_am_i` skill: "who am I?" / "wer bin ich" → identified speaker.

### Add to PA-36 (UI) — mobile + analytics

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-69 | Story | Mobile-responsive browser UI | S10 | **Done** |
| PA-70 | Story | Keyboard-free mode (pure voice) | S10 | **Done** |
| PA-71 | Story | High-contrast / accessibility theme | S10 | **Done** |
| PA-72 | Story | Skill usage stats panel | S12 | **Done** |
| PA-73 | Story | Response latency graph per session | S12 | **Done** |

### Add to PA-40 (Integrations) — music + communication

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-74 | Story | Spotify play / pause / next / previous | S8 | **Done** |
| PA-75 | Story | System volume up / down / mute | S8 | **Done** |
| PA-76 | Story | Screenshot by voice — saved to Desktop | S8 | **Done** |
| PA-77 | Story | "What song is playing?" via Spotify API | S8 | **Done** |
| PA-89 | Task  | Train custom "Hey Plasma" wake word model | Backlog | **Done** |
| PA-78 | Story | Slack — read latest message in channel | S13 | To Do |
| PA-79 | Story | Microsoft Teams — meeting summary by voice | S13 | To Do |
| PA-80 | Story | Send WhatsApp message by voice | S13 | To Do |

### Add to PA-44 (Infra) — packaging + release

| Key | Type | Summary | Sprint | Status |
|---|---|---|---|---|
| PA-81 | Task  | Auto-update mechanism (check GitHub releases) | S15 | **Done** |
| PA-82 | Story | First-run setup wizard (mic test, model download) | S14 | **Done** |
| PA-83 | Task  | Public documentation site (GitHub Pages) | S15 | **Done** |
| PA-84 | Task  | Changelog generation (conventional commits) | S15 | **Done** |
| PA-85 | Task  | v1.0.0 release tag + changelog | S16 | **Done** |
| PA-86 | Task  | Demo video for README | S16 | To Do |

---

## Sprint plan (May 13 → Dec 15)

| Sprint | Dates | Goal | Tickets | State |
|---|---|---|---|---|
| S1 | May 13 – May 27 | Cloud LLM | PA-28, PA-29, PA-30, PA-31 | Done |
| S2 | May 27 – Jun 10 | UI essentials | PA-37, PA-38, PA-39 | Done |
| S3 | Jun 10 – Jun 24 | Wake word | PA-34, PA-35 | Done |
| S4 | Jun 24 – Jul 8 | Skills batch 1 | PA-53, PA-54, PA-55, PA-56 | Done |
| S5 | Jul 8 – Jul 22 | Skills batch 2 | PA-57, PA-58, PA-59 | Done |
| S6 | Jul 22 – Aug 5 | Outlook | PA-41, PA-42, PA-43 | Done |
| S7 | Aug 5 – Aug 19 | Productivity skills | PA-60, PA-61, PA-62, PA-63 | Done |
| S8 | Aug 19 – Sep 2 | Music & media | PA-74, PA-75, PA-76, PA-77 | Done |
| S9 | Sep 2 – Sep 16 | Multi-language | PA-48, PA-50, PA-51, PA-52 | **Done** |
| S10 | Sep 16 – Sep 30 | Mobile UI | PA-69, PA-70, PA-71 | **Done** |
| S11 | Oct 1 – Oct 15 | Voice profiles | PA-65, PA-66, PA-67 | **Done** |
| S12 | Oct 15 – Oct 29 | Analytics + memory UI | PA-68, PA-72, PA-73 | **Done** |
| S13 | Oct 29 – Nov 12 | Slack / Teams / WhatsApp | PA-78, PA-79, PA-80 | To Do |
| S14 | Nov 12 – Nov 26 | Packaging & CI | PA-45, PA-46, PA-82 | **Done** |
| S15 | Nov 26 – Dec 10 | Auto-update & docs | PA-81, PA-83, PA-84, PA-64 | **Done** |
| S16 | Dec 10 – Dec 15 | v1.0 release | PA-32, PA-85, PA-86 | Partial (PA-32, PA-86 outstanding) |

---

## Completed — S3 (Jun 10 – Jun 24)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-34 | Story | "Hey Plasma" detection via openWakeWord | **Done** |
| PA-35 | Task  | Remove F9 hotkey once wake word is stable | **Done** |

**Live tested:** "Hey Jarvis" → score=0.65/0.78 → auto-record → "What time is it?" → skill match → TTS reply. Full hands-free loop working.

---

## Completed — S4 (Jun 24 – Jul 8)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-53 | Story | Timer skill — "set a timer for 5 minutes" | **Done** |
| PA-54 | Story | Calculator skill — math by voice | **Done** |
| PA-55 | Story | Joke skill — random joke on demand | **Done** |
| PA-56 | Story | Unit converter — "convert 5 miles to km" | **Done** |

**Live tested:** all four skills triggered by voice. 22 unit tests passing.

---

## Completed — S5 (Jul 8 – Jul 22)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-57 | Story | Wikipedia lookup — "who is Einstein" | **Done** |
| PA-58 | Story | Translation skill — "say hello in French" | **Done** |
| PA-59 | Story | Reminder skill — "remind me at 3pm" | **Done** |

**Tests:** 23 unit tests in `tests/test_sprint5_skills.py`. Full suite: 101 passing.
**Files:** `backend/skills/wikipedia_lookup.py`, `backend/skills/translator.py`, `backend/skills/reminder.py`

---

## Completed — S6 (Jul 22 – Aug 5)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-41 | Story | Read today's Outlook calendar events by voice | **Done** |
| PA-42 | Story | Read unread Outlook email count | **Done** |
| PA-43 | Story | "Add to calendar" by voice | **Done** |

**Auth:** MSAL device-code flow, token cached at `.plasma/ms_token.json` (gitignored).
**Setup:** `python scripts/ms_auth.py` — one-time, then all three skills work by voice.
**Tests:** 21 unit tests in `tests/test_sprint6_skills.py`. Full suite: 122 passing.

---

## Completed — S8 (Aug 19 – Sep 2)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-75 | Story | Volume up/down/mute via Windows WScript | **Done** |
| PA-76 | Story | Screenshot → saved to Desktop as PNG | **Done** |
| PA-74 | Story | Spotify play/pause/next/previous | **Done** |
| PA-77 | Story | "What song is playing?" | **Done** |

**Volume:** subprocess + PowerShell WScript.Shell key codes, no extra packages.
**Screenshot:** Pillow ImageGrab, saved to `~/Desktop/screenshot_YYYYMMDD_HHMMSS.png`.
**Spotify:** spotipy OAuth, one-time setup via `scripts/spotify_auth.py`.
  Requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET in .env, Spotify Premium for playback control.
**PA-89 logged:** "Hey Plasma" custom wake word — needs openWakeWord model training, backlog.
**Tests:** 18 new; full suite 165 passing.

---

## Completed — S7 (Aug 5 – Aug 19)

| Ticket | Type | Summary | Status |
|---|---|---|---|
| PA-60 | Story | Voice notes — "take a note: …" | **Done** |
| PA-61 | Story | Todo list — add / read / clear by voice | **Done** |
| PA-62 | Story | News via RSS feeds | **Done** |
| PA-63 | Story | Weather forecast — 5-day | **Done** |

**Storage:** notes → `.plasma/notes.jsonl`, todos → `.plasma/todos.json` (both gitignored).
**News:** BBC World RSS, falls back to BBC main feed. No API key.
**Forecast:** Open-Meteo `daily` endpoint, 5 days, reuses weather geocoding.
**Tests:** 25 new tests; full suite 147 passing.

---

## Commit convention

```
PA-29: add Groq client with streaming first-sentence
PA-28: add PII redaction layer before cloud call
```

---

## Workflow rules

- **Bug found** → Bug under its epic, link `is blocked by`, flag `Impediment` if sprint-blocking
- **Feature done** → Done in this file + commit hash in description
- **Sprint end** → move remaining To Do items back to backlog, plan next sprint
- **Session end** → this file must reflect reality
