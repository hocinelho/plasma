# Meeting notes

Plasma can sit through a meeting, transcribe it, and write Word minutes.

## Using it

| Say | What happens |
|---|---|
| "start meeting notes" | Begins recording and transcribing. |
| "start meeting notes about *the fibre rollout*" | Same, with that as the title. |
| "meeting status" | How long it has been running, how many segments. |
| "stop the meeting" | Stops, summarizes, writes the `.docx`. |
| "protokoll starten" / "meeting beenden" | German equivalents. |

The minutes land in `.plasma/meetings/<title>.docx`, next to the raw
transcript (`<meeting-id>.jsonl`).

## Before you record other people

Recording a conversation is regulated in most places, and in **Germany
recording confidential spoken word without consent is a criminal offence**
(§201 StGB) — it is not enough that you are a participant. Tell everyone at
the start and get their agreement. Plasma's "recording now" reply is worded
to prompt exactly that; don't remove it.

## What the document contains

1. **Summary** — 2–4 sentences.
2. **Key points**, **Decisions**, **Open questions** — bulleted.
3. **Action items** — a table of task + owner.
4. **Full transcript** — every segment with an `[HH:MM]` timestamp.

## How it works

```
mic → AudioCapture (own stream, 16 kHz)
    → 25-second segments
    → silence check (RMS) — quiet segments are never sent to Whisper,
      which would otherwise hallucinate text from room tone
    → Whisper → segment appended to .plasma/meetings/<id>.jsonl immediately
    ↓ on "stop"
    → LLM summarizes into structured JSON
    → python-docx renders the minutes
```

**Segments are written to disk as they finish**, so a crash, a reload or a
closed laptop lid costs you at most the last 25 seconds. A finished meeting
can be rebuilt from its JSONL with `recorder.load(meeting_id)`.

## Behaviour when things are missing

- **No LLM reachable** → the document is still written, with the transcript
  and a visible note that the summary could not be produced. It never invents
  decisions.
- **`python-docx` not installed** → the transcript is still saved; the spoken
  reply says the Word file could not be written and why.
- **No microphone** → recording stops with an error in `status()`.

## Limits worth knowing

- It records **your microphone**. For a Teams/Zoom call, the other side is
  only captured if it comes out of your speakers into the mic — proper
  system-audio capture is a separate job.
- There are **no speaker labels**. Whisper gives text, not "who said it".
  Plasma's speaker ID exists for short commands, but attributing every line
  of a long meeting is a bigger piece of work.
- Whisper mishears names and jargon; the transcript is a good record, not a
  legal one.
