# Plasma Avatar — Design Brief (creature / mascot)

> For the dedicated **avatar session**. Read `HANDOFF.md` first, then this.
> Goal: turn Plasma's abstract sphere into a **creature/mascot companion** with
> personality, while keeping everything offline, self-contained, and cheap.
>
> Branch: `claude/avatar-design` off `claude/enhance-plasma-project-cOZli`.
> Own PR into the enhance branch. Coordinate with the main session via git +
> this doc + `HANDOFF.md` — the two sessions do NOT share memory.

---

## Direction (decided by Hocine, 2026-07)

A **creature / mascot** — a distinct little character with a persona (robot
companion / friendly droid vibe fits Plasma's "local, loyal, yours" identity),
NOT a human face and NOT just the abstract orb. It should feel alive: idle
breathing/blinking, reactions to wake, listening, thinking, speaking, and
proactive moments (greets you, looks tired when you do). Think a desk
companion, on-brand with the sci-fi JARVIS aesthetic — not cartoonish/off-brand.

---

## What exists today (must be preserved or cleanly replaced)

The current avatar is an abstract **glass-node Fibonacci sphere** drawn on a
`<canvas id="avatar" width="150" height="150">`, initialized by `initAvatar()`
inside `frontend/index.html`. It is driven by a small, stable **contract** that
the rest of the app already calls — keep these exact hooks working so you don't
have to touch the backend or the voice pipeline:

| Signal | Where set | Meaning — drive your mascot from these |
|---|---|---|
| `avatarState` | `setStatus()` ~line 906 | `'idle' \| 'listening' \| 'thinking' \| 'speaking'` — the mascot's core mood |
| `avatarLevel` (0..1) | lip-sync tick ~line 1065, wake ~1193 | live audio amplitude while speaking → mouth/pulse/bounce |
| `window.avatarWakeBurst(ms=1700)` | called on wake ~line 1187 | play a "waking up" reaction |
| `window.bgWakeBurst()` | background canvas ~line 795 | full-page wake flash (leave to bg-canvas) |
| `PALETTE[state]` | ~line 615 | per-state colour/mood palette — reuse the idea |

Audio path already exists: playback is routed through a Web Audio `analyser`
(`fftSize:256`) that feeds `avatarLevel` — so **lip-sync / mouth movement is
free**, just map `avatarLevel` to a mouth or bounce.

Constraints already honored (keep them):
- **`prefers-reduced-motion`** → the current code drops to a static state; your
  mascot must too (a calm idle, no animation loop churn).
- Pure **canvas 2D + requestAnimationFrame**, no libraries, no network.

---

## Hard constraints (do not break)

- **Self-contained**: all HTML/CSS/JS/assets inline or as `data:` URIs. No CDN,
  no external fonts/images, no fetch. Plasma runs fully offline.
- **Cheap on CPU**: the machine is a modest laptop already running Whisper +
  Ollama + MediaPipe. Budget the avatar at a few % CPU. Prefer a small sprite
  sheet or lightweight vector/canvas drawing over per-frame heavy math. Pause
  the RAF when the tab is hidden (`document.hidden`) — the see-through view
  already does this; match it.
- **Theme-aware**: works on the app's dark UI (and light if toggled).
- **Accessible**: `aria-hidden="true"` on the canvas is fine (decorative), but
  don't remove the visible status text elsewhere.
- **~150×150 slot** in the header today — you may grow it, but keep the layout
  from breaking on mobile (`frontend/camera.html` is the phone page).

---

## Recommended plan (avoids colliding with the main session)

The main session is actively editing `frontend/index.html` (tracking overlay)
and the backend. **To avoid merge conflicts, extract first:**

1. **Extract** the current avatar out of `index.html` into its own
   `frontend/avatar.js` (+ `frontend/avatar.css`), exposing the same contract
   (`avatarState`, `avatarLevel`, `avatarWakeBurst`). Replace the inline
   `initAvatar()` with a `<script src="/avatar.js">` include. Small, mechanical
   PR — land it first so both sessions have a clean seam.
   - Note: `index.html` is served by `backend/main.py`'s `/` route; static
     sibling files need a route or `StaticFiles` mount — check how `camera.html`
     / `style.css` are served (there's a 404 on `/style.css` today) and wire
     `/avatar.js` the same way.
2. **Design the mascot** in `avatar.js`: idle (breathing + occasional blink),
   listening (ears/antenna perk, leans in), thinking (looks up, dots), speaking
   (mouth/bounce driven by `avatarLevel`), wake (the `avatarWakeBurst` reaction),
   plus optional proactive: happy greet, "tired" droop (mirror the sleepy
   alert). Start from a **style sheet / concept** (a few PNG/SVG frames as data
   URIs, or parametric canvas) — pick one art style and commit to it.
3. **Iterate visually** with the `artifact-design` skill / screenshots
   (headless Chromium is available — the existing UI was verified that way).
4. Keep a running **`docs/avatar-status.md`** (like `locate-vision-status.md`)
   so progress is visible to the other session.

## Open questions for Hocine (ask via the avatar session)

- Mascot species/vibe: little **robot/droid**, glowing **wisp/elemental**, or
  an **animal-like** companion? (Robot fits the brand best.)
- Name/personality on screen, or stays the voice only?
- Always a mascot, or mascot ↔ orb toggle (some users prefer the minimal orb)?

## Coordination checklist (both sessions)

- Avatar work → `claude/avatar-design` branch, own draft PR into the enhance branch.
- Touch **only** `frontend/avatar.*`, the one `<script>`/route line in
  `index.html`, and `docs/avatar-*.md`. Leave backend + tracking overlay to the
  main session.
- If you must change shared `index.html` regions, ping via `HANDOFF.md` note.
