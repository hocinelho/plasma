"""She meets someone new: notices, asks their name, and keeps the answer.

Greeting a face she had been *told* about already worked. This is the
unprompted half — the difference between a lookup table and actually meeting
someone — and it spans three files, so most of what can break is the seams
between them rather than any one function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.modules.vision import face_id, introductions  # noqa: E402


class TestReadingTheAnswer:
    """"Hocine" is a complete answer to "what's your name?", and there is
    nothing else in it to go on."""

    @pytest.mark.parametrize("said", [
        "Hocine",
        "My name is Hocine",
        "I'm Hocine",
        "I am Hocine",
        "It's Hocine",
        "Call me Hocine",
        "Hocine.",
        "  hocine  ",
        "Ich heiße Hocine",
        "Mein Name ist Hocine",
        "Ich bin Hocine",
    ])
    def test_it_finds_the_name(self, said):
        assert face_id.parse_offered_name(said) == "Hocine"

    def test_it_normalises_the_capitalisation(self):
        """The name is spoken, so its case comes from Whisper's guess — and
        it becomes a folder on disk and the word she says back."""
        assert face_id.parse_offered_name("HOCINE") == "Hocine"

    def test_accented_and_hyphenated_names_survive(self):
        assert face_id.parse_offered_name("Zoë") == "Zoë"
        assert face_id.parse_offered_name("Anne-Marie") == "Anne-marie"

    @pytest.mark.parametrize("said", [
        "no", "No.", "nope", "nein", "stop", "cancel", "later",
        "who are you", "why do you want to know", "what",
        "I would rather not say", "none of your business",
    ])
    def test_a_refusal_is_not_a_name(self, said):
        """Enrolling a face as "No" would be permanent, and would have to be
        found and deleted by hand. Declining must leave nothing saved."""
        assert face_id.parse_offered_name(said) is None

    def test_a_greeting_back_is_not_a_name(self):
        """"Hello" has exactly the shape of a name and is the single most
        likely thing to be said to a talking avatar."""
        assert face_id.parse_offered_name("hello") is None
        assert face_id.parse_offered_name("hallo") is None

    def test_a_whole_sentence_is_not_a_name(self):
        assert face_id.parse_offered_name("that is a strange question to ask") is None

    def test_empty_input_is_not_a_name(self):
        assert face_id.parse_offered_name("") is None
        assert face_id.parse_offered_name(None) is None

    def test_it_is_separate_from_the_unprompted_parser(self):
        """parse_enroll_command fires out of ordinary conversation and has to
        be sure; this one only runs on the turn after she asked, where a bare
        name is the expected answer. Loosening the strict one to accept bare
        names would enrol a face every time somebody said a word."""
        assert face_id.parse_enroll_command("Hocine") is None
        assert face_id.parse_offered_name("Hocine") == "Hocine"


class TestPacing:
    def test_she_waits_before_speaking(self):
        """Frames arrive at ~6/s. Reacting to one frame would fire at anyone
        walking past the camera, and at a single bad recognition of somebody
        she does know."""
        assert introductions.STRANGER_FRAMES >= 6

    def test_she_does_not_ask_twice_in_a_row(self):
        """Being asked your name twice in a minute is worse than not being
        asked. The commonest reason for no answer is not wanting to give
        one."""
        assert introductions.ASK_COOLDOWN_S >= 120

    def test_the_marker_names_the_skill_that_handles_it(self):
        """chat_service splits the pending fact on the first ':' to find the
        skill. A prefix that is not a real skill name routes the answer
        nowhere, silently."""
        skill_name = introductions.AWAITING_NAME.split(":")[0]
        assert (ROOT / "backend" / "skills" / f"{skill_name}.py").is_file()

    def test_the_question_is_asked_in_both_languages(self):
        assert introductions.question(de=False) != introductions.question(de=True)
        assert "?" in introductions.question(de=False)
        assert "?" in introductions.question(de=True)


class TestArming:
    def test_arming_survives_a_broken_memory(self, monkeypatch):
        """She has already spoken by the time this runs. Failing to arm means
        the answer is treated as ordinary conversation — poor, but never a
        reason to raise into the perception loop."""
        import backend.modules.router.chat_service as cs
        monkeypatch.setattr(cs, "get_memory",
                            lambda: (_ for _ in ()).throw(RuntimeError("no db")))
        assert introductions.arm("s1") is False

    def test_arming_replaces_an_earlier_question(self, monkeypatch):
        """Two queued introductions would mean the second answer resolving
        the first question."""
        import backend.modules.router.chat_service as cs

        facts = [{"id": 7, "content": introductions.AWAITING_NAME}]
        deleted, added = [], []

        class _Mem:
            def get_facts(self, category=None, limit=None):
                return list(facts)

            def delete_fact(self, fid):
                deleted.append(fid)

            def add_fact(self, **kw):
                added.append(kw)

        monkeypatch.setattr(cs, "get_memory", _Mem)
        assert introductions.arm("s1") is True
        assert deleted == [7]
        assert added and added[0]["content"] == introductions.AWAITING_NAME

    def test_it_leaves_other_pending_intents_alone(self, monkeypatch):
        """An alarm waiting for a time is a different conversation."""
        import backend.modules.router.chat_service as cs

        deleted = []

        class _Mem:
            def get_facts(self, category=None, limit=None):
                return [{"id": 3, "content": "alarm:awaiting_time"}]

            def delete_fact(self, fid):
                deleted.append(fid)

            def add_fact(self, **kw):
                pass

        monkeypatch.setattr(cs, "get_memory", _Mem)
        introductions.arm("s1")
        assert deleted == []


class TestTheSeams:
    """Each of these is a place where the three files have to agree, and
    where disagreeing produces no error — just an answer that goes nowhere."""

    def test_the_router_passes_the_pending_state_to_the_skill(self):
        """Without it the skill cannot tell "this is an answer to my
        question" from "this is a fresh request", because a bare name looks
        like neither."""
        src = (ROOT / "backend" / "modules" / "router" / "chat_service.py").read_text(
            encoding="utf-8")
        block = src.split("Pending intent →", 1)[1][:1200]
        assert '"pending": fact["content"]' in block

    def test_the_skill_reads_that_state(self):
        src = (ROOT / "backend" / "skills" / "vision_query.py").read_text(
            encoding="utf-8")
        assert 'get("pending") == AWAITING_NAME' in src
        assert "parse_offered_name" in src

    def test_the_socket_asks_and_arms_together(self):
        """Asking without arming leaves the answer to fall through to the
        LLM; arming without asking silently swallows the next thing said."""
        src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        block = src.split("ask a stranger who they are", 1)[1][:900]
        assert "introductions.question(de)" in block
        assert "introductions.arm(" in block

    def test_it_only_fires_when_recognition_actually_works(self):
        """Without DeepFace installed identify() returns None for everybody,
        so this would ask the same person their name every five minutes for
        ever."""
        src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        block = src.split("ask a stranger who they are", 1)[1][:900]
        assert "face_id.is_available()" in block
        assert "not cached_identity" in block

    def test_it_only_fires_when_the_user_asked_to_be_recognised(self):
        """Reading a face is opt-in (identify:true); asking about one is more
        so."""
        src = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        block = src.split("ask a stranger who they are", 1)[1][:900]
        assert 'data.get("identify")' in block
