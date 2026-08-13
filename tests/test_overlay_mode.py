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

    def test_she_does_not_wander_out_of_a_small_window(self):
        js = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")
        assert "classList.contains('overlay')" in js


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
