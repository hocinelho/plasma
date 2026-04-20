@"
# Plasma — Private Working Memory

**Last updated:** 2026-04-20
**Current step:** 1 — project skeleton (in progress)

---

## What we built
- Project folder structure (backend/, frontend/, .plasma/, docs/, tests/)
- .gitignore with Python + PyCharm + private memory exclusions
- Public README.md with roadmap
- This MEMORY.md (private, git-ignored)
- Step 1 is underway; GitHub remote not yet created

## What's in progress
- Finishing Step 1: requirements.txt, git init, first commit, GitHub remote, open in PyCharm

## What's next (ordered)
1. Finish Step 1 -> git init + GitHub remote + PyCharm open
2. Step 2 -> FastAPI backend stub with /health + /ws voice endpoint
3. Step 3 -> Local SQLite memory layer (FTS5 schema + CRUD)
4. Step 4 -> Local router (Ollama + pick model: Qwen 3 3B vs Gemma 3 4B)
5. Step 5 -> Whisper ASR integration (faster-whisper, CPU first)
6. Step 6 -> Piper TTS integration
7. Step 7 -> Skill system design + unit-test gate
8. Step 8 -> USER.md bootstrap + periodic-nudge loop
9. Step 9 -> Cloud escalation path + PII redaction + audit log
10. Step 10 -> Plasma orb frontend
11. Step 11 -> Windows integration (PowerShell, Outlook, Calendar)
12. Step 12 -> MCP clients

## Open questions / missing
- Which local model: Qwen 3 3B vs Gemma 3 4B vs Llama 3.2 3B -> decide at Step 4
- ASR on CPU: faster-whisper small or base? -> decide at Step 5
- TTS voice: English only first, or German too? (Hocine works in DE market)
- GPU available on dev machine? -> affects model size choices
- GitHub account / repo name -> need to create at end of Step 1

## Decisions log
- 2026-04-20: Project name = Plasma
- 2026-04-20: Target OS = Windows (PyCharm, PowerShell, Docker optional)
- 2026-04-20: Memory strategy = dual file (public README.md + private MEMORY.md)
- 2026-04-20: Architecture = System 1 (local) + System 2 (cloud) hybrid
- 2026-04-20: Backend = FastAPI (consistent with Einblasen stack)

## Key files (as we create them)
- README.md -> public roadmap
- .plasma/MEMORY.md -> this file
- .gitignore
- (requirements.txt coming next)

## Conversation resume protocol
If returning after a break, paste this file into the chat and say:
"Here is where we are on Plasma. Continue from current step."

## Session handoff notes
- Next session should start by confirming current step and reviewing 'What's next'
- If a step is half-done, the 'What's in progress' section lists the exact stopping point
"@ | Out-File -FilePath .plasma\MEMORY.md -Encoding utf8