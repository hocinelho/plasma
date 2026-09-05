"""Queued movement must belong to the turn that asked for it.

Say "hello" and she performed her entire 19-clip repertoire. The cause was not
in the trigger matching at all: self_test() calls run(), and tell_secret's and
show_abilities' run() queue avatar movement. Loading 49 skills at startup
therefore left "secret" plus the full showcase sitting in the queue before the
user had said a word, and the first message of the session — any message —
popped it.

Two things kept it alive:
  * requests during self-test were honoured at all;
  * an expired entry was reported as absent but left in place, so it waited
    for the next request to refresh the shared timestamp and rode along.
"""
import time

import pytest

from backend.modules import avatar_state


@pytest.fixture(autouse=True)
def clean():
    avatar_state.clear()
    yield
    avatar_state.clear()


class TestLoadTimeLeak:
    def test_loading_the_real_skills_queues_nothing(self):
        """The actual bug, end to end.

        Before the fix this left animation='secret' and a 19-clip routine
        waiting, and the user's first message — whatever it was — popped them.
        """
        from backend.modules.skills.registry import SkillRegistry

        avatar_state.clear()
        SkillRegistry().load_all()

        assert avatar_state.pop_gesture() is None
        assert avatar_state.pop_animation() is None
        assert avatar_state.pop_routine() is None

    def test_self_tests_that_verify_queueing_still_pass(self):
        """avatar_move's self_test queues and pops on purpose. Blocking
        requests during self-test would break it, so the queue is cleared
        afterwards instead."""
        from backend.modules.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.load_all()
        assert registry.find_by_trigger("wave at me") is not None

    def test_the_clear_is_in_a_finally(self):
        """A skill whose self_test raises must not leave its movement queued."""
        import pathlib
        src = (pathlib.Path(avatar_state.__file__).parents[1]
               / "modules" / "skills" / "registry.py").read_text(encoding="utf-8")
        block = src.split("if not self_test():", 1)[1][:600]
        assert "finally:" in block
        assert "avatar_state.clear()" in block


class TestExpiry:
    def test_an_expired_entry_is_discarded_not_kept(self):
        avatar_state.request_animation("jump")
        assert avatar_state.pop_animation(max_age_s=-1) is None
        # The old code returned None here but left "jump" queued, so the next
        # request refreshed it back into life.
        assert avatar_state.pop_animation(max_age_s=9999) is None

    def test_each_slot_ages_independently(self):
        """One shared timestamp meant queueing anything rejuvenated everything."""
        avatar_state.request_animation("jump")
        time.sleep(0.05)
        avatar_state.request_gesture("thumbup")
        # The gesture is younger than the animation; ageing the animation out
        # must not be prevented by the newer gesture.
        assert avatar_state.pop_animation(max_age_s=0.01) is None
        assert avatar_state.pop_gesture(max_age_s=9999) == "thumbup"

    def test_a_fresh_entry_survives(self):
        avatar_state.request_routine(["jump", "waving"])
        assert avatar_state.pop_routine(max_age_s=30) == ["jump", "waving"]


def test_a_greeting_does_not_inherit_a_showcase():
    """What the user actually saw: "hello" answered with all 19 clips."""
    avatar_state.request_animation("secret")            # tell_secret.self_test
    avatar_state.request_routine(sorted(avatar_state.known_animations()))
    avatar_state.clear()                                # what the registry now does

    # First user message of the session.
    assert avatar_state.pop_gesture() is None
    assert avatar_state.pop_animation() is None
    assert avatar_state.pop_routine() is None
