"""Talking over her must cut her off.

Behaviour verified in a real browser (she stops mid-clip, the turn is released
in ~0.4 s instead of the full 3 s of audio, and the mic starts even with
isBusy held true the way sendAudio holds it). What is pinned here is the
wiring that makes it possible, because every piece of it is a place where the
old code deliberately did the opposite.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
AVATAR = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")


class TestTheAvatarStops:
    def test_the_renderer_exposes_a_stop(self):
        assert "window.avatarStopSpeaking = () =>" in AVATAR
        assert "head.stopSpeaking()" in AVATAR

    def test_stopping_also_kills_the_queued_routine(self):
        """Cut off and then carrying on with a dance is worse than not
        stopping at all."""
        # Anchor on the definition: the `delete` in the fallback path comes
        # first in the file.
        block = AVATAR.split("window.avatarStopSpeaking = () =>", 1)[1][:600]
        assert "stopRoutine()" in block
        assert "pendingRoutine = null" in block
        assert "head.stopAnimation()" in block

    def test_it_is_removed_on_fallback(self):
        """Dropping to the mascot renderer must not leave a dead global that
        the page then calls into."""
        assert "delete window.avatarStopSpeaking;" in AVATAR


class TestThePageStops:
    def test_the_audio_element_is_reachable_to_stop_it(self):
        """It used to be a local inside playBase64Audio — nothing outside
        could pause it."""
        assert "let speakingAudio" in INDEX
        assert "speakingAudio = audio;" in INDEX
        block = INDEX.split("function interruptSpeech()", 1)[1][:700]
        assert "speakingAudio.pause()" in block

    def test_the_pending_turn_is_released_immediately(self):
        """sendAudio awaits playback. Without ending that promise the mic
        stays locked until audio that will never play finishes."""
        block = INDEX.split("function interruptSpeech()", 1)[1][:700]
        assert "speakingFinish()" in block
        assert "isBusy = false;" in block

    def test_playback_completion_is_idempotent(self):
        """An interrupt and the real onended can both fire."""
        block = INDEX.split("function playBase64Audio", 1)[1][:900]
        assert "if (done) return;" in block


class TestTheMicWins:
    def test_reaching_for_the_mic_interrupts_before_the_busy_check(self):
        """isBusy is exactly what she is doing while speaking — checking it
        first is what locked the mic out for the whole reply."""
        block = INDEX.split("function startRecording()", 1)[1][:500]
        interrupt_at = block.index("interruptSpeech()")
        busy_at = block.index("if (isBusy) return")
        assert interrupt_at < busy_at

    def test_still_refuses_while_she_is_thinking(self):
        """Only speech is interruptible; a request already in flight is not."""
        block = INDEX.split("function startRecording()", 1)[1][:500]
        assert "if (isBusy) return;" in block

    def test_the_wake_word_can_interrupt_too(self):
        """Saying "hey Plasma" over her is the most natural barge-in there is,
        and it was gated on the same isBusy."""
        assert "if (!isRecording && (!isBusy || isSpeaking))" in INDEX


class TestNothingIsForgotten:
    def test_the_reply_is_stored_before_it_is_spoken(self):
        """"Without forgetting what she told before": handle_chat writes the
        assistant turn to memory before TTS is ever called, so an interrupted
        reply is still in her history in full."""
        service = (ROOT / "backend" / "modules" / "router"
                   / "chat_service.py").read_text(encoding="utf-8")
        add = service.index('memory.add_message(session_id, "assistant", reply)')
        assert add > 0
        main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        # TTS happens in the endpoint, after handle_chat has returned.
        assert main.index("handle_chat") < main.index("tts_synthesize")

    def test_an_interrupt_does_not_stamp_idle_over_listening(self):
        assert "if (!wasInterrupted) setStatus('idle');" in INDEX

    def test_the_flag_resets_each_turn(self):
        block = INDEX.split("async function sendAudio", 1)[1][:400]
        assert "wasInterrupted = false;" in block
