"""Tests for overlay mode (/?overlay=1) and the Android companion that hosts it.

Overlay mode is stage mode with every opaque surface removed, so the Android
floating window composites her straight onto your home screen. The failure it
guards against is subtle and ugly: one element still painting a background
turns her window into a dark rectangle sitting on the wallpaper.

The Kotlin cannot be compiled here (no Android SDK), so what is checked is the
manifest and configuration — the parts that silently disable the app rather
than failing to build.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "avatar.css").read_text(encoding="utf-8")
ANDROID = ROOT / "android"
MANIFEST = (ANDROID / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")


class TestOverlayPage:
    def test_overlay_parameter_is_read(self):
        assert "params.get('overlay') === '1'" in INDEX

    def test_overlay_implies_summon(self):
        """It must also go full screen and open the mic, like ?stage=1."""
        assert "const summoned = overlay ||" in INDEX

    def test_backdrop_is_removed(self):
        """The plasma nebula is opaque — it would be a dark box on the wallpaper."""
        assert "body.overlay #bg-canvas { display: none !important; }" in CSS

    def test_page_paints_no_background(self):
        assert "html.overlay, body.overlay" in CSS
        assert "background-color: transparent !important;" in CSS

    def test_in_page_exit_button_is_hidden(self):
        """The Android window owns dismissal; two controls would confuse."""
        assert "body.overlay #stage-exit { display: none !important; }" in CSS

    def test_she_does_not_wander_on_her_own(self):
        """She used to drift side to side on a timer in stage mode — in a
        190px Android window that walked her out of her own window. She now
        never moves without being asked to or reacting to something, in any
        stage: no autonomous position drift anywhere in the renderer."""
        js = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")
        assert "holder.style.transform = `translateX" not in js
        assert "function wander(" not in js

    def test_the_only_thing_she_does_unprompted_is_breathe(self):
        """Ambient motion used to be a random pick from every idle-* clip, so
        she shifted and fidgeted between conversations. Standing and waiting
        is the whole behaviour asked for: one calm clip, chosen, not rolled."""
        js = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")
        assert "const AMBIENT = 'idle-breathing';" in js
        body = js.split("function ambientClip(", 1)[1].split("}", 1)[0]
        assert "Math.random" not in body


class TestAndroidManifest:
    def test_requests_the_overlay_permission(self):
        assert "android.permission.SYSTEM_ALERT_WINDOW" in MANIFEST

    def test_declares_a_microphone_foreground_service(self):
        """Android 14 refuses to start it otherwise, and she must keep hearing
        you while another app is in front."""
        assert 'android:foregroundServiceType="microphone"' in MANIFEST
        assert "FOREGROUND_SERVICE_MICROPHONE" in MANIFEST

    def test_cleartext_stays_off(self):
        """The mic needs a secure context; plain http would break her silently."""
        assert 'android:usesCleartextTraffic="false"' in MANIFEST

    def test_service_is_not_exported(self):
        assert 'android:name=".OverlayService"' in MANIFEST
        assert 'android:exported="false"' in MANIFEST


class TestAndroidCertificateHandling:
    """The tempting shortcut here is handler.proceed() on any SSL error, which
    would make the app trust whatever answers on that address."""

    SERVICE = (ANDROID / "app" / "src" / "main" / "java" / "com" / "plasma"
               / "companion" / "OverlayService.kt").read_text(encoding="utf-8")

    def test_pins_the_certificate(self):
        assert "prefs.certPin" in self.SERVICE
        assert "MessageDigest.getInstance(\"SHA-256\")" in self.SERVICE

    def test_rejects_a_different_host(self):
        assert "host != expectedHost" in self.SERVICE

    def test_cancels_on_a_changed_certificate(self):
        assert "handler.cancel()" in self.SERVICE

    def test_changing_the_address_clears_the_pin(self):
        prefs = (ANDROID / "app" / "src" / "main" / "java" / "com" / "plasma"
                 / "companion" / "Prefs.kt").read_text(encoding="utf-8")
        assert "if (cleaned != serverUrl) certPin = null" in prefs


def test_readme_states_it_is_untested_on_a_device():
    """It was written against the docs and never run — say so."""
    readme = (ANDROID / "README.md").read_text(encoding="utf-8")
    assert "never been run" in readme


class TestTurningIsRealNotMimed:
    """"She is not turning, only doing the movement of turning left."

    Exactly right. TalkingHead retargets bone rotations and drops root
    motion, so the Mixamo turn clips animated the FOOTWORK of a turn and left
    her facing precisely where she started. The clip supplies the steps; the
    renderer has to supply the turn.
    """

    JS = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")

    def test_the_clip_also_rotates_her(self):
        block = self.JS.split("const p = head.playAnimation(", 1)[1][:600]
        assert "TURN_DEGREES[name]" in block
        assert "avatarTurn" in block

    def test_left_and_right_go_opposite_ways(self):
        line = [ln for ln in self.JS.splitlines() if "const TURN_DEGREES" in ln][0]
        assert "'turn-left': 90" in line and "'turn-right': -90" in line

    def test_two_left_turns_make_a_half_turn(self):
        """"Turn around" and "I need to see your back" are two turn-left
        clips, so the rotation has to accumulate rather than snap to a fixed
        heading."""
        block = self.JS.split("window.avatarTurn =", 1)[1][:300]
        assert "armature.rotation.y + deg" in block

    def test_she_can_be_brought_back_round(self):
        assert "window.avatarFaceFront" in self.JS

    def test_face_front_arrives_as_a_gesture(self):
        """It travels on the gesture channel, which already delivers one-shot
        instructions to the browser — so the renderer must intercept it
        before looking it up in the rig, where it does not exist."""
        block = self.JS.split("window.avatarGesture =", 1)[1][:500]
        assert "'face-front'" in block
        assert block.index("'face-front'") < block.index("gestureTemplates")

    def test_it_rotates_the_armature_not_the_page(self):
        """The holder is a DOM element containing a WebGL canvas — a CSS
        transform would rotate the flat picture of her, not her."""
        block = self.JS.split("function turnTo(", 1)[1][:600]
        assert "armature.rotation.y" in block
        assert "style.transform" not in block
