"""Tests for PA-106/107 — LocateAnything skill + Muapi image generation (all I/O mocked)."""
from __future__ import annotations
import json
import sys
import types
from unittest.mock import MagicMock, patch
import numpy as np
import pytest


def _make_resp(json_data, status=200):
    r = MagicMock()
    r.raise_for_status.return_value = r
    r.json.return_value = json_data
    r.status_code = status
    return r


def _ec(**over):
    """Fake config with both skills configured."""
    c = MagicMock()
    c.LOCATE_ANYTHING_BIN = "/fake/locate-anything-cli"
    c.LOCATE_ANYTHING_MODEL = "/fake/model.gguf"
    c.LOCATE_ANYTHING_MODE = "hybrid"
    c.LOCATE_ANYTHING_TIMEOUT = 60.0
    c.LOCATE_ANYTHING_SERVER_URL = ""   # local CLI mode by default
    c.LOCATE_ANYTHING_THREADS = 0
    c.CAMERA_DEVICE = 0
    c.MUAPI_API_KEY = "key123"
    c.MUAPI_BASE_URL = "https://api.muapi.ai"
    c.MUAPI_IMAGE_MODEL = "flux-schnell"
    c.MUAPI_TIMEOUT = 10.0
    for k, v in over.items():
        setattr(c, k, v)
    return c


# ───────────────────────────── LocateAnything ──────────────────────────────────

def test_locate_extract_object_en():
    from backend.skills.locate import _extract_object
    assert _extract_object("find my keys") == "keys"
    assert _extract_object("where is my phone") == "phone"
    assert _extract_object("can you see my coffee mug") == "coffee mug"


def test_locate_extract_object_de():
    from backend.skills.locate import _extract_object
    assert _extract_object("finde meinen schlüssel") == "schlüssel"
    assert _extract_object("wo ist mein handy") == "handy"


def test_locate_extract_object_none():
    from backend.skills.locate import _extract_object
    # No object after the trigger
    assert _extract_object("find") is None or _extract_object("find") == ""


def test_locate_not_configured():
    from backend.skills.locate import run
    with patch("backend.core.config.config",
               _ec(LOCATE_ANYTHING_BIN="", LOCATE_ANYTHING_MODEL="", LOCATE_ANYTHING_SERVER_URL="")):
        result = run({"utterance": "find my keys"})
    assert "isn't set up" in result.lower() or "locate_anything" in result.lower() or "set up" in result.lower()


def test_locate_describe_location_center():
    from backend.skills.locate import _describe_location
    # Box centered in a 600x400 image
    loc = _describe_location([250, 150, 100, 100], 600, 400, de=False)
    assert "center" in loc.lower()


def test_locate_describe_location_left():
    from backend.skills.locate import _describe_location
    loc = _describe_location([0, 150, 50, 50], 600, 400, de=False)
    assert "left" in loc.lower()


def test_locate_found_object():
    from backend.skills import locate as loc_mod

    detections = [{"label": "keys", "box": [250, 150, 100, 100]}]
    fake_frame = np.zeros((400, 600, 3), dtype=np.uint8)

    cv2_mock = types.ModuleType("cv2")
    cv2_mock.imwrite = MagicMock(return_value=True)

    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.locate.snapshot" if False else "backend.modules.vision.capture.snapshot",
               return_value=fake_frame), \
         patch.dict(sys.modules, {"cv2": cv2_mock}), \
         patch("backend.skills.locate._run_detection", return_value=detections):
        result = loc_mod.run({"utterance": "find my keys"})

    assert "keys" in result.lower()
    assert "found" in result.lower() or "see" in result.lower()


def test_locate_object_not_found():
    from backend.skills import locate as loc_mod

    fake_frame = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2_mock = types.ModuleType("cv2")
    cv2_mock.imwrite = MagicMock(return_value=True)

    with patch("backend.core.config.config", _ec()), \
         patch("backend.modules.vision.capture.snapshot", return_value=fake_frame), \
         patch.dict(sys.modules, {"cv2": cv2_mock}), \
         patch("backend.skills.locate._run_detection", return_value=[]):
        result = loc_mod.run({"utterance": "find my keys"})

    assert "can't see" in result.lower() or "keys" in result.lower()


def test_locate_run_detection_parses_json(tmp_path):
    """_run_detection should parse the JSON file written by the CLI (local mode)."""
    from backend.skills import locate as loc_mod

    out_json = {"detections": [{"label": "mug", "box": [10, 20, 30, 40]}]}

    def fake_subprocess_run(cmd, **kwargs):
        out_idx = cmd.index("--output") + 1
        from pathlib import Path
        Path(cmd[out_idx]).write_text(json.dumps(out_json), encoding="utf-8")
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    # Force local mode (no server URL)
    with patch("backend.core.config.config", _ec(LOCATE_ANYTHING_SERVER_URL="")), \
         patch("backend.skills.locate.subprocess.run", side_effect=fake_subprocess_run):
        dets = loc_mod._run_detection("/fake/img.png", "mug")

    assert dets == out_json["detections"]


def test_locate_run_detection_nonzero_exit():
    from backend.skills import locate as loc_mod

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "model load error"
        proc.stdout = ""
        return proc

    # Force local mode (no server URL)
    with patch("backend.core.config.config", _ec(LOCATE_ANYTHING_SERVER_URL="")), \
         patch("backend.skills.locate.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="locate-anything-cli failed"):
            loc_mod._run_detection("/fake/img.png", "mug")


def test_locate_self_test():
    from backend.skills.locate import self_test
    assert self_test()


def test_locate_meta():
    from backend.skills.locate import META
    assert META["name"] == "locate"
    assert any("find my" in t for t in META["triggers"])
    assert any("wo ist" in t for t in META["triggers"])


# ───────────────────────────── Image generation ────────────────────────────────

def test_imagegen_extract_prompt_en():
    from backend.skills.image_gen import _extract_prompt
    assert _extract_prompt("generate an image of a sunset") == "a sunset"
    # "draw a cat..." — the leading article is consumed; subject is preserved
    assert _extract_prompt("draw a cat wearing a hat") == "cat wearing a hat"


def test_imagegen_extract_prompt_de():
    from backend.skills.image_gen import _extract_prompt
    p = _extract_prompt("generiere ein bild von einem berg")
    assert "berg" in p.lower()


def test_imagegen_extract_prompt_empty():
    from backend.skills.image_gen import _extract_prompt
    assert _extract_prompt("generate an image") is None


def test_imagegen_not_configured():
    from backend.skills.image_gen import run
    with patch("backend.core.config.config", _ec(MUAPI_API_KEY="")):
        result = run({"utterance": "generate an image of a sunset"})
    assert "isn't set up" in result.lower() or "muapi" in result.lower()


def test_imagegen_async_poll_success():
    from backend.skills import image_gen as ig

    submit_resp = _make_resp({"request_id": "abc123"})
    poll_resp = _make_resp({"status": "completed", "outputs": ["https://cdn.muapi.ai/out.png"]})

    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.image_gen.http_post", return_value=submit_resp), \
         patch("backend.skills.image_gen.http_get", return_value=poll_resp), \
         patch("backend.skills.image_gen.time.sleep"):
        result = ig.run({"utterance": "generate an image of a sunset"})

    assert "out.png" in result
    assert "sunset" in result.lower()


def test_imagegen_sync_url_in_submit():
    """Some models return the URL directly in the submit response."""
    from backend.skills import image_gen as ig

    submit_resp = _make_resp({"outputs": ["https://cdn.muapi.ai/direct.png"]})

    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.image_gen.http_post", return_value=submit_resp):
        result = ig.run({"utterance": "draw a cat"})

    assert "direct.png" in result


def test_imagegen_poll_failed_status():
    from backend.skills import image_gen as ig

    submit_resp = _make_resp({"request_id": "abc"})
    poll_resp = _make_resp({"status": "failed", "error": "nsfw"})

    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.image_gen.http_post", return_value=submit_resp), \
         patch("backend.skills.image_gen.http_get", return_value=poll_resp), \
         patch("backend.skills.image_gen.time.sleep"):
        result = ig.run({"utterance": "generate an image of a dog"})

    assert "failed" in result.lower()


def test_imagegen_network_error():
    from backend.skills import image_gen as ig

    def boom(*a, **kw):
        raise ConnectionError("offline")

    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.image_gen.http_post", side_effect=boom):
        result = ig.run({"utterance": "generate an image of a sunset"})

    assert "failed" in result.lower()


def test_imagegen_extract_url_variants():
    from backend.skills.image_gen import _extract_url
    assert _extract_url({"outputs": ["u1"]}) == "u1"
    assert _extract_url({"images": [{"url": "u2"}]}) == "u2"
    assert _extract_url({"output": "u3"}) == "u3"
    assert _extract_url({"data": {"outputs": ["u4"]}}) == "u4"
    assert _extract_url({"nothing": 1}) is None


def test_imagegen_de_response():
    from backend.skills import image_gen as ig

    submit_resp = _make_resp({"outputs": ["https://cdn.muapi.ai/berg.png"]})
    with patch("backend.core.config.config", _ec()), \
         patch("backend.skills.image_gen.http_post", return_value=submit_resp):
        result = ig.run({"utterance": "generiere ein bild von einem berg", "language": "de"})

    assert "berg.png" in result
    assert "dein bild" in result.lower() or "hier" in result.lower()


def test_imagegen_self_test():
    from backend.skills.image_gen import self_test
    assert self_test()


def test_imagegen_meta():
    from backend.skills.image_gen import META
    assert META["name"] == "image_gen"
    assert any("generate an image" in t for t in META["triggers"])
    assert any("generiere" in t for t in META["triggers"])
