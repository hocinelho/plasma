"""Two things from the 2026-09-05 list, both visible in the session log.

"SHE DOESN'T TAKE ALL MY TALK." Every recording came back as exactly
`duration 00:06.000`, because the microphone closed on a flat six-second
stopwatch whether or not anyone was still speaking. A sentence is not a fixed
length, so a fixed timer is the wrong instrument — anything longer than six
seconds was cut in half, every single time.

"OPEN GMAIL." Declined, and the model explained it could not open
applications. Two reasons at once: there was no gmail entry in the table, and
the name pattern did not allow hyphens, so "Open G-Mail." — which is how a
transcriber writes what was said — failed to match at all.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

from backend.skills import open_app  # noqa: E402


def _resolve(utterance: str):
    """The app name open_app would settle on, without launching anything."""
    u = utterance.lower().strip()
    m = re.search(
        r"(?:open|launch|start)\s+([a-z][a-z -]*?)"
        r"(?:\s+(?:for me|please|now))?\s*[.!?]?\s*$", u)
    if not m:
        return None
    name = re.sub(r"^(?:a|the)\s+", "", m.group(1).strip())
    name = open_app._ALIASES.get(
        name, open_app._ALIASES.get(name.replace("-", " "), name))
    if name in open_app._NOT_AN_APP:
        return "DECLINE"
    return name


class TestOpeningGmail:
    def test_gmail_exists_at_all(self):
        assert "gmail" in open_app.APPS

    def test_the_way_whisper_actually_writes_it(self):
        """Straight from the log: `Transcribed: text='Open G-Mail.'`"""
        assert _resolve("Open G-Mail.") == "gmail"

    def test_the_other_spellings_reach_the_same_place(self):
        for said in ("open gmail", "open g mail", "open google mail",
                     "Can you open Gmail please"):
            assert _resolve(said) == "gmail", said

    def test_the_pattern_allows_hyphens_now(self):
        """Without this the whole match failed, so the skill declined and the
        LLM answered — which is why it looked like a missing feature rather
        than a missing hyphen."""
        assert _resolve("open you-tube") == "youtube"

    def test_the_apps_asked_for_in_the_same_breath(self):
        for said, expected in [("open teams", "teams"),
                               ("open whats app", "whatsapp"),
                               ("open drive", "drive"),
                               ("open calendar", "calendar")]:
            assert _resolve(said) == expected, said

    def test_ordinary_speech_still_declines(self):
        """The aliases must not turn "start over" into an application."""
        assert _resolve("start over") == "DECLINE"

    def test_every_alias_points_at_something_real(self):
        """An alias to a name that is not in APPS resolves to nothing and
        reports "I don't know how to open gmial" — worse than no alias."""
        for alias, target in open_app._ALIASES.items():
            assert target in open_app.APPS, f"{alias!r} -> {target!r} is not an app"


class TestSheWaitsForYouToFinish:
    def test_the_hard_cap_is_no_longer_a_sentence_length(self):
        line = [ln for ln in INDEX.splitlines() if "const WAKE_AUTO_STOP_MS" in ln][0]
        ms = int(line.split("=")[1].split(";")[0].strip())
        assert ms >= 20000, "6s cut every long sentence in half"

    def test_she_stops_on_silence_not_on_a_stopwatch(self):
        assert "function watchForSilence()" in INDEX
        block = INDEX.split("function watchForSilence()", 1)[1][:1400]
        assert "getByteTimeDomainData" in block
        assert "SILENCE_HOLD_MS" in block

    def test_it_waits_before_it_starts_judging(self):
        """The pause between the wake word and the first word of the sentence
        would otherwise end the recording before it had begun."""
        assert "MIN_SPEECH_MS" in INDEX
        block = INDEX.split("function watchForSilence()", 1)[1][:1400]
        assert "started > MIN_SPEECH_MS" in block

    def test_the_silence_hold_is_a_pause_not_a_hesitation(self):
        line = [ln for ln in INDEX.splitlines() if "const SILENCE_HOLD_MS" in ln][0]
        ms = int(line.split("=")[1].split(";")[0].strip())
        assert 1000 <= ms <= 2500

    def test_it_only_applies_hands_free(self):
        """Hold-to-talk and tap-to-stop already have a person deciding when
        the sentence ended; cutting them off on a pause takes that away."""
        block = INDEX.split("mediaRecorder.start();", 1)[1][:400]
        assert "inConversation()" in block and "watchForSilence()" in block

    def test_stopping_cancels_the_watcher(self):
        """A loop left running against a closed recorder is a leak that only
        shows up as the next recording ending instantly."""
        block = INDEX.split("function stopRecording()", 1)[1][:500]
        assert "stopWatchingForSilence()" in block
        assert "clearTimeout(wakeStopTimer)" in block
