"""Tests for the wallpaper studio (/wallpaper).

The page itself is WebGL, so its rendering is verified in a real browser
rather than here. What these tests hold down is the wiring that browser
testing cannot see: the route exists, the file it serves exists, and the
handful of contracts the page depends on are still true — chiefly that the
vendored TalkingHead renderer keeps its drawing buffer, without which every
exported wallpaper comes back blank.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "wallpaper.html"
VENDOR = ROOT / "frontend" / "vendor" / "talkinghead" / "talkinghead.mjs"


def test_page_exists():
    assert PAGE.is_file(), "frontend/wallpaper.html is missing"


def test_route_is_registered():
    """The route must be declared, whether or not the app can boot here."""
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/wallpaper")' in main


def test_route_serves_the_page():
    app = pytest.importorskip("backend.main", reason="app deps not installed").app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        res = client.get("/wallpaper")
    assert res.status_code == 200
    assert "Wallpaper Studio" in res.text


def test_renderer_preserves_the_drawing_buffer():
    """Without this the export silently produces an empty PNG.

    The default WebGL context is free to discard its colour buffer once the
    frame is composited, so canvas.toDataURL() afterwards reads nothing. This
    is a local patch to vendored code — easy to lose on the next vendor
    refresh, hence a test rather than a comment alone.
    """
    src = VENDOR.read_text(encoding="utf-8")
    assert "preserveDrawingBuffer: true" in src


def test_page_uses_the_local_import_map():
    """Everything is served from this machine — no CDN, per Plasma's design."""
    html = PAGE.read_text(encoding="utf-8")
    assert "/vendor/three/three.module.js" in html
    assert "/vendor/talkinghead/talkinghead.mjs" in html
    assert "cdn." not in html.split("<script type=\"module\">")[0]


def test_clip_names_are_restricted_before_becoming_a_url():
    """Animation names go straight into a fetch path — keep them constrained."""
    html = PAGE.read_text(encoding="utf-8")
    assert "/^[a-z0-9][a-z0-9-]*$/.test(name)" in html


def test_export_restores_the_on_screen_renderer():
    """The preview must survive an export: resize out, then straight back."""
    html = PAGE.read_text(encoding="utf-8")
    assert "head.onResize()" in html
    assert "r.setPixelRatio(head.opt.modelPixelRatio" in html


def test_main_page_links_to_the_studio():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'href="/wallpaper"' in index
