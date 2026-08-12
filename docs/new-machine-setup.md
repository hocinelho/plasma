# Setting Plasma up on a different computer

`git clone` gives you the code. It does **not** give you your data — several
things are deliberately gitignored, and two of them are irreplaceable.

## 1. Copy these off the old machine first

| Path | What it is | Replaceable? |
|---|---|---|
| `.plasma/memory.sqlite` | Everything she has learned about you | **No** — gone if lost |
| `.plasma/USER.md` | Your generated profile | **No** |
| `.plasma/models/hey_plasma.onnx` | Your custom wake word | **Hard** — has to be retrained |
| `.plasma/meetings/` | Past meeting transcripts + minutes | **No** |
| `.env` | Your settings and API keys | Rewritable from `.env.example` |
| `voices/*.onnx` | Piper TTS voices | Yes — re-downloadable |

`.plasma` is a **hidden folder on Windows**. To get at it, paste the path
into Explorer's address bar rather than trying to browse to it:

```
C:\Users\<you>\PycharmProjects\plasma\.plasma
```

Copy the whole `.plasma` folder, `voices`, and `.env` to the same place on
the new machine. If you can still reach the old laptop at all, do this before
anything else.

## 2. Install Python first

If PowerShell answers `python -m venv` with *"Python wurde nicht gefunden"* /
*"Python was not found"* and offers the Microsoft Store, Python is not
installed — that message is a stub Windows ships in its place. Everything
after it (`pip`, `Activate.ps1`) then fails for the same reason.

Get **Python 3.11 or 3.12** from [python.org/downloads](https://www.python.org/downloads/windows/):

- tick **"Add python.exe to PATH"** on the first screen;
- **"Install for me only"** needs no administrator rights.

Close PowerShell and open it again — PATH changes only apply to new windows.
Check with `python --version`.

Avoid 3.13 for now: several of Plasma's dependencies ship no wheels for it
yet and would have to compile from source.

## 3. Set up the new machine

```powershell
git clone https://github.com/hocinelho/plasma.git
cd plasma
git checkout claude/avatar-design

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install python-docx          # meeting minutes
```

Then paste in `.plasma`, `voices` and `.env` from step 1.

If `Activate.ps1` is refused with a *running scripts is disabled* error,
PowerShell's execution policy is blocking it. Allow it for that window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 4. Things that live outside the project

- **Ollama** — install from [ollama.ai](https://ollama.ai), then
  `ollama pull mistral:latest` (or whichever model your `.env` names).
- **Whisper** — downloads itself on first run, no action needed.
- **A voice**, if you skipped copying `voices/`:
  `python scripts/download_female_voice.py kristin`

## 5. Check it

```powershell
python run_plasma.py
```

Open <http://localhost:8000/setup> — it reports which pieces are working.
Then ask her *"what do you remember?"*: if she knows you, the memory came
across intact.

## Which branch?

`claude/avatar-design` — it carries the 3D avatar, the motion clips, meeting
notes and the phone support. The other branches are older.

## Without administrator rights

The one thing that needs admin is the firewall rule for phone access
(port 8443). Everything else — Python, the models, Ollama, Plasma itself —
installs per-user and does not.

If you cannot add the rule:

- **On the PC itself, everything still works.** `http://localhost:8000` needs
  no firewall change at all.
- For the phone, Windows usually shows a one-time *"Allow access?"* prompt
  the first time a program listens on a port. Accepting that prompt creates
  the rule; it appears when `serve_phone.py` first binds.
- Failing that, a phone hotspot sometimes works where a corporate LAN does
  not, but the firewall still applies — the rule is the real requirement.
