"""Tests for the character picker — choosing which avatar she wears.

The promise the picker makes is that swapping the face costs you nothing:
every character plays every Mixamo clip, because the renderer retargets them
onto whichever skeleton is loaded. That part is verified in a real browser
(frame-to-frame pixel movement while a clip plays, per character); what is
pinned here is the wiring around it.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AVATAR_JS = (ROOT / "frontend" / "avatar.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
AVATARS = ROOT / "frontend" / "avatars"


from backend.modules.avatar_state import discover_models


class TestDiscovery:
    def test_route_is_registered(self):
        main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        assert '@app.get("/api/avatar/models")' in main

    def test_lists_what_is_on_disk(self):
        data = discover_models()
        files = [m["file"] for m in data["models"]]
        assert "brunette.glb" in files, "the shipped character must always appear"
        assert data["default"] in files
        for m in data["models"]:
            assert m["url"] == f"/avatars/{m['file']}"
            assert m["label"].strip()
            assert m["body"] in ("F", "M")

    def test_an_unlisted_glb_still_appears(self, tmp_path):
        """Dropping a .glb in with no avatars.json entry must just work —
        otherwise adding a character looks like it did nothing."""
        (tmp_path / "my-hero.glb").write_bytes(b"glTF fake")
        data = discover_models(tmp_path)
        assert [m["file"] for m in data["models"]] == ["my-hero.glb"]
        assert data["models"][0]["label"] == "My Hero"      # readable fallback
        assert data["models"][0]["body"] == "F"             # sane default
        assert data["default"] == "my-hero.glb"

    def test_a_broken_metadata_file_costs_labels_not_characters(self, tmp_path):
        (tmp_path / "a.glb").write_bytes(b"x")
        (tmp_path / "avatars.json").write_text("{ this is not json", encoding="utf-8")
        data = discover_models(tmp_path)
        assert [m["file"] for m in data["models"]] == ["a.glb"]
        assert data["models"][0]["label"] == "A"

    def test_a_default_naming_a_missing_file_falls_back(self, tmp_path):
        """A stale _default would otherwise leave the stage empty."""
        (tmp_path / "b.glb").write_bytes(b"x")
        (tmp_path / "avatars.json").write_text(
            json.dumps({"_default": "deleted.glb"}), encoding="utf-8")
        assert discover_models(tmp_path)["default"] == "b.glb"

    def test_a_bogus_body_value_is_not_passed_through(self, tmp_path):
        (tmp_path / "c.glb").write_bytes(b"x")
        (tmp_path / "avatars.json").write_text(
            json.dumps({"c.glb": {"body": "banana"}}), encoding="utf-8")
        assert discover_models(tmp_path)["models"][0]["body"] == "F"

    def test_empty_folder_is_not_an_error(self, tmp_path):
        assert discover_models(tmp_path) == {"models": [], "default": None}

    def test_missing_folder_is_not_an_error(self, tmp_path):
        assert discover_models(tmp_path / "nope") == {"models": [], "default": None}


class TestAvatarsJson:
    def test_parses(self):
        meta = json.loads((AVATARS / "avatars.json").read_text(encoding="utf-8"))
        assert meta["_default"] == "brunette.glb"

    def test_default_exists_on_disk(self):
        meta = json.loads((AVATARS / "avatars.json").read_text(encoding="utf-8"))
        assert (AVATARS / meta["_default"]).is_file()

    def test_only_the_licence_clean_model_is_committed(self):
        """Four of the five sample characters are non-commercial and this repo
        is public. Only brunette.glb ships; the rest are fetched by the user.

        Asks git what is TRACKED rather than what is on disk. The two were the
        same thing until the fetch script existed, and using the working
        directory made this test fail the moment somebody ran it — which is
        the normal, intended state, not a regression.
        """
        import subprocess
        tracked = subprocess.run(
            ["git", "ls-files", "frontend/avatars/*.glb"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        ).stdout.split()
        assert [Path(p).name for p in tracked] == ["brunette.glb"]

    def test_entries_declare_a_body_type(self):
        meta = json.loads((AVATARS / "avatars.json").read_text(encoding="utf-8"))
        for key, entry in meta.items():
            if key.startswith("_"):
                continue
            assert entry["body"] in ("F", "M"), key


class TestRendererContract:
    def test_exposes_the_switch(self):
        assert "window.avatarSetModel = async (file)" in AVATAR_JS
        assert "window.avatarModels = ()" in AVATAR_JS

    def test_fallback_removes_them(self):
        """Dropping to the mascot renderer must not leave dead globals behind
        that the picker would then call into."""
        assert "delete window.avatarSetModel;" in AVATAR_JS
        assert "delete window.avatarModels;" in AVATAR_JS

    def test_choice_is_remembered(self):
        assert "localStorage.setItem(MODEL_KEY, file)" in AVATAR_JS

    def test_storage_failure_is_survivable(self):
        """Private browsing throws on localStorage — she must still load."""
        assert "catch (e) { return ''; }" in AVATAR_JS

    def test_swap_reapplies_framing_and_mood(self):
        """showAvatar() replaces the armature, so anything set against the old
        one is gone — a swap that skipped this left her neutral and mis-framed."""
        assert "head.setView(lastView)" in AVATAR_JS
        assert "head.setMood(MOODS[window.avatarState]" in AVATAR_JS

    def test_swap_restarts_idle_motion(self):
        assert "if (clips.idle && clips.idle.length) scheduleIdle();" in AVATAR_JS

    def test_concurrent_swaps_are_refused(self):
        """Two loads at once would race to own the armature."""
        assert "if (!head || failed || switching) return false;" in AVATAR_JS


class TestPickerUI:
    def test_markup_exists_and_starts_hidden(self):
        assert 'id="avatar-picker" hidden' in INDEX
        assert 'id="avatar-select"' in INDEX

    def test_stays_hidden_without_a_real_choice(self):
        assert "if (!models || models.length < 2) return;" in INDEX

    def test_shows_progress_while_loading(self):
        """These models run to 36 MB — a silent wait reads as a freeze."""
        assert "'loading…'" in INDEX

    def test_restores_the_selection_when_a_load_fails(self):
        assert "select.value = state.current;" in INDEX


class TestChoosingFromTheUrl:
    """The picker remembers your choice in localStorage, which is
    per-browser — and the desktop overlay is its own browser, with its own
    storage and no room to draw a picker in a 220px window. Choosing a
    character in Chrome therefore left the overlay exactly as it was, with no
    way in."""

    def test_the_page_accepts_a_model_parameter(self):
        assert "get('model')" in INDEX
        block = INDEX.split("get('model')", 1)[1][:600]
        assert "avatarSetModel" in block

    def test_it_waits_for_the_renderer(self):
        """avatarSetModel exists only once the first .glb has loaded, so
        firing immediately does nothing and says nothing."""
        block = INDEX.split("get('model')", 1)[1][:700]
        assert "setTimeout" in block

    def test_the_overlay_launcher_passes_it_through(self):
        src = (ROOT / "scripts" / "desktop_overlay.py").read_text(encoding="utf-8")
        assert "PLASMA_OVERLAY_MODEL" in src
        assert "&model=" in src

    def test_the_filename_is_url_encoded(self):
        """It goes straight into a query string, and .glb filenames can carry
        spaces."""
        src = (ROOT / "scripts" / "desktop_overlay.py").read_text(encoding="utf-8")
        block = src.split("PLASMA_OVERLAY_MODEL", 1)[1][:400]
        assert "quote(model)" in block


class TestTheOtherCharactersAreFetchable:
    """"We used to have 4 other avatars and a button to change it."

    Correct, and the picker was never the problem. The control, the labels
    for all five and the retargeting were all built; what was never in the
    repo is the four .glb files. discover_models() therefore returned one
    entry and the picker hides itself when there is nothing to choose —
    indistinguishable, from the outside, from the feature not existing.
    """

    def test_there_is_one_command_that_gets_them(self):
        assert (ROOT / "scripts" / "get_avatars.py").is_file()

    def test_it_fetches_every_character_the_labels_promise(self):
        """avatars.json names five. A label with no file behind it is what
        made this look like a missing feature."""
        src = (ROOT / "scripts" / "get_avatars.py").read_text(encoding="utf-8")
        meta = json.loads((AVATARS / "avatars.json").read_text(encoding="utf-8"))
        promised = {k for k in meta if k.endswith(".glb")}
        shipped = {"brunette.glb"}
        for name in promised - shipped:
            assert name in src, f"{name} is labelled but never fetched"

    def test_it_pins_a_commit_not_a_branch(self):
        """Upstream's main moving would silently change which characters
        arrive, months later, with nothing in this repo having changed."""
        src = (ROOT / "scripts" / "get_avatars.py").read_text(encoding="utf-8")
        assert re.search(r'COMMIT = "[0-9a-f]{40}"', src)

    def test_it_states_the_licences(self):
        """Only one of the five is free for commercial use, and it is not the
        one that ships. Downloading them without saying so would be handing
        someone a licensing problem quietly."""
        src = (ROOT / "scripts" / "get_avatars.py").read_text(encoding="utf-8")
        assert "CC0" in src and "Non-commercial" in src

    def test_the_binaries_stay_out_of_git(self):
        """62 MB of non-commercially-licensed binaries in a public repo."""
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "frontend/avatars/*.glb" in ignore

    def test_but_the_shipped_one_stays_tracked(self):
        """A fresh clone has to have somebody to be, before any download."""
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "!frontend/avatars/brunette.glb" in ignore
        assert (AVATARS / "brunette.glb").is_file()

    def test_a_partial_download_is_never_left_behind(self):
        """discover_models() picks up any .glb on disk, so a truncated file
        becomes a character that fails to load in the browser with nothing to
        say why."""
        src = (ROOT / "scripts" / "get_avatars.py").read_text(encoding="utf-8")
        assert ".part" in src and "rename(target)" in src
