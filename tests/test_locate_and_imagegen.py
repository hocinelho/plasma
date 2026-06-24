"""Tests for PA-106/107 — LocateAnything skill (3-tier) + Muapi image generation."""
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
    """Fake config — cloud vision enabled by default (tier 1), CLI disabled."""
    c = MagicMock()
    # Cloud (tier 1) — enabled by default so _is_available() returns True
    c.CLOUD_API_KEY = "fake-cloud-key"
    c.CLOUD_MODEL = "gemini-2.0-flash"
    c.CLOUD_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Ollama vision (tier 2) — disabled by default
    c.LOCATE_VISION_OLLAMA_MODEL = ""
    c.OLLAMA_BASE_URL = "http://localhost:11434"
    # CLI (tier 3) — disabled by default
    c.LOCATE_ANYTHING_BIN = ""
    c.LOCATE_ANYTHING_MODEL = ""
    c.LOCATE_ANYTHING_MODE = "hybrid"
    c.LOCATE_ANYTHING_TIMEOUT = 60.0
    c.LOCATE_ANYTHING_SERVER_URL = ""
    c.LOCATE_ANYTHING_THREADS = 0
    # Camera
    c.CAMERA_DEVICE = 0
    # Image gen
    c.MUAPI_API_KEY = "key123"
    c.MUAPI_BASE_URL = "https://api.muapi.ai"
    c.MUAPI_IMAGE_MODEL = "flux-schnell"
    c.MUAPI_TIMEOUT = 10.0
    for k, v in over.items():
        setattr(c, k, v)
    return c


def _cv2_mock():
    m = types.ModuleType("cv2")
    m.imwrite = MagicMock(return_value=True)
    m.IMWRITE_JPEG_QUALITY = 1
    return m


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
    assert _extract_object("find") is None or _extract_object("find") == ""


def test_locate_not_configured():
    """All three tiers disabled → skill reports not configured."""
    from backend.skills.locate import run
    cfg = _ec(CLOUD_API_KEY="", LOCATE_VISION_OLLAMA_MODEL="",
              LOCATE_ANYTHING_BIN="", LOCATE_ANYTHING_MODEL="",
              LOCATE_ANYTHING_SERVER_URL="")
    with patch("backend.core.config.config", cfg):
        result = run({"utterance": "find my keys"})
    assert "set up" in result.lower() or "cloud_api_key" in result.lower() or "isn't" in result.lower()


def test_locate_describe_location_center():
    from backend.skills.locate import _describe_location
    loc = _describe_location([250, 150, 100, 100], 600, 400, de=False)
    assert "center" in loc.lower()


def test_locate_describe_location_left():
    from backend.skills.locate import _describe_location
    loc = _describe_location([0, 150, 50, 50], 600, 400, de=False)
    assert "left" in loc.lower()


def test_locate_cloud_vision_tier1():
    """Tier 1: cloud vision returns a natural language location."""
    from backend.skills import locate as loc_mod

    fake_frame = np.zeros((400, 600, 3), dtype=np.uint8)
    cloud_resp = _make_resp({"choices": [{"message": {"content": "I can see your keys on the left side of the image."}}]})

    with patch("backend.core.config.config", _ec()), \
         patch("backend.modules.vision.capture.snapshot", return_value=fake_frame), \
         patch.dict(sys.modules, {"cv2": _cv2_mock()}), \
         patch("backend.skills.locate.http_post", return_value=cloud_resp):
        result = loc_mod.run({"utterance": "find my keys"})

    assert "keys" in result.lower()
    assert "left" in result.lower()


def test_locate_ollama_tier2():
    """Tier 2: Ollama moondream used when cloud key absent."""
    from backend.skills import locate as loc_mod

    fake_frame = np.zeros((400, 600, 3), dtype=np.uint8)
    ollama_resp = _make_resp({"response": "Your keys are in the center of the image."})

    cfg = _ec(CLOUD_API_KEY="", LOCATE_VISION_OLLAMA_MODEL="moondream")
    with patch("backend.core.config.config", cfg), \
         patch("backend.modules.vision.capture.snapshot", return_value=fake_frame), \
         patch.dict(sys.modules, {"cv2": _cv2_mock()}), \
         patch("backend.skills.locate.http_post", return_value=ollama_resp):
        result = loc_mod.run({"utterance": "find my keys"})

    assert "keys" in result.lower() or "center" in result.lower()


def test_locate_cli_tier3_parses_json(tmp_path):
    """Tier 3: CLI subprocess — parses JSON output file."""
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

    cfg = _ec(CLOUD_API_KEY="", LOCATE_VISION_OLLAMA_MODEL="",
              LOCATE_ANYTHING_BIN="/fake/cli", LOCATE_ANYTHING_MODEL="/fake/model.gguf",
              LOCATE_ANYTHING_SERVER_URL="")
    with patch("backend.core.config.config", cfg), \
         patch("backend.skills.locate.subprocess.run", side_effect=fake_subprocess_run):
        result = loc_mod._locate_via_cli("/fake/img.png", "mug", 600, 400, False)

    assert "mug" in result.lower()


def test_locate_cli_tier3_nonzero_exit():
    """Tier 3: CLI nonzero exit raises RuntimeError."""
    from backend.skills import locate as loc_mod

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "model load error"
        proc.stdout = ""
        return proc

    cfg = _ec(CLOUD_API_KEY="", LOCATE_VISION_OLLAMA_MODEL="",
              LOCATE_ANYTHING_BIN="/fake/cli", LOCATE_ANYTHING_MODEL="/fake/model.gguf",
              LOCATE_ANYTHING_SERVER_URL="")
    with patch("backend.core.config.config", cfg), \
         patch("backend.skills.locate.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="locate-anything-cli failed"):
            loc_mod._locate_via_cli("/fake/img.png", "mug", 600, 400, False)


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
