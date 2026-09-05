"""Waking her should buy a conversation, not one sentence.

Reported plainly: "why do I have to keep telling Hey Jarvis — she should keep
waking up like for 15 seconds". A wake used to cover exactly one turn: she
answered, went back to sleep, and the follow-up needed her name again. Nobody
talks like that; "and tomorrow?" is the normal shape of a conversation and it
was the one thing you could not say without saying her name first.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


class TestTheWindow:
    def test_a_wake_opens_it(self):
        block = INDEX.split("if (msg.type === 'wake')", 1)[1][:1400]
        assert "keepListening()" in block

    def test_she_reopens_the_mic_when_she_stops_talking(self):
        assert "listenAgainIfStillTalking" in INDEX

    def test_the_reopen_happens_after_the_turn_is_released(self):
        """isBusy stays true until the finally block, and reopening refuses
        while she is busy — called a line earlier it silently does nothing."""
        finally_block = INDEX.split("} finally {", 1)[1][:500]
        assert finally_block.index("isBusy = false") < \
            finally_block.index("listenAgainIfStillTalking()")

    def test_a_real_exchange_extends_it(self):
        """So a conversation lasts as long as it is actually going."""
        block = INDEX.split("const data = await r.json();", 1)[1][:700]
        assert "if (data.transcript) keepListening();" in block

    def test_silence_does_not_extend_it(self):
        """The reopened mic records six seconds whether or not anyone speaks.
        Extending on those would leave it reopening for ever in an empty
        room — the window has to be able to close."""
        block = INDEX.split("const data = await r.json();", 1)[1][:700]
        keep = block.index("keepListening()")
        # The extension is guarded by there being a transcript at all.
        assert "data.transcript" in block[max(0, keep - 60):keep]

    def test_starting_to_talk_by_hand_opens_it_too(self):
        """Tapping her should also buy a conversation, not one sentence."""
        assert "function startTalking()" in INDEX
        block = INDEX.split("function startTalking()", 1)[1][:200]
        assert "keepListening()" in block and "startRecording()" in block

    def test_the_automatic_reopen_does_not_extend_the_window(self):
        """startRecording() is how the automatic reopen happens. If it
        extended the window, the window could never close: reopen, record
        silence, extend, reopen... The extension lives in startTalking(),
        which only a person calls."""
        body = INDEX.split("function startRecording()", 1)[1].split("\nfunction ", 1)[0]
        assert "keepListening()" not in body

    def test_stopping_by_hand_ends_the_conversation(self):
        """Tapping to stop is a person saying "I am done" — she must not
        reopen the microphone a second later."""
        block = INDEX.split("btn.addEventListener('click'", 1)[1][:300]
        assert "endConversation()" in block

    def test_the_window_is_long_enough_to_think_but_short_enough_to_end(self):
        line = [ln for ln in INDEX.splitlines() if "const FOLLOW_UP_MS" in ln][0]
        ms = int(line.split("=")[1].strip().rstrip(";"))
        assert 8000 <= ms <= 30000
