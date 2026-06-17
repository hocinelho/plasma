"""Tests covering:
- Smart home skill (mocked Home Assistant API)
- Weather skill HTTP paths (mocked)
- Weather forecast skill HTTP paths (mocked)
- Translator skill HTTP paths (mocked) + timeout bug fix
- http_client.post added
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_resp(json_data, status=200):
    r = MagicMock()
    r.raise_for_status.return_value = r  # supports chaining: resp.raise_for_status().json()
    r.json.return_value = json_data
    r.status_code = status
    return r


# ── http_client.post ──────────────────────────────────────────────────────────

def test_http_client_has_post():
    from backend.core.http_client import post
    assert callable(post)


# ═══════════════════════════════════════════════════════════════════════════════
# Smart Home (Home Assistant)
# ═══════════════════════════════════════════════════════════════════════════════

def test_smart_home_not_configured():
    from backend.skills.smart_home import run
    with patch("backend.skills.smart_home.config") as cfg:
        cfg.HA_TOKEN = ""
        result = run({"utterance": "turn on the lights"})
    assert "not configured" in result.lower() or "HA_TOKEN" in result


def test_smart_home_turn_on_calls_service():
    from backend.skills.smart_home import run
    captured = {}

    def fake_post(url, *, timeout=6.0, **kw):
        captured["url"] = url
        captured["payload"] = kw.get("json", {})
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok123"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "turn on the lights"})

    assert "on" in result.lower() or "eingeschaltet" in result.lower()
    assert "services/light/turn_on" in captured["url"]
    assert captured["payload"]["entity_id"] == "light.all"


def test_smart_home_turn_off_calls_service():
    from backend.skills.smart_home import run

    def fake_post(url, *, timeout=6.0, **kw):
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "turn off the lights"})

    assert "off" in result.lower() or "ausgeschaltet" in result.lower()


def test_smart_home_room_resolves_entity():
    from backend.skills.smart_home import run
    captured = {}

    def fake_post(url, *, timeout=6.0, **kw):
        captured["payload"] = kw.get("json", {})
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        run({"utterance": "turn on the bedroom lights"})

    assert captured["payload"]["entity_id"] == "light.bedroom"


def test_smart_home_dim_sets_brightness():
    from backend.skills.smart_home import run
    captured = {}

    def fake_post(url, *, timeout=6.0, **kw):
        captured["payload"] = kw.get("json", {})
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "dim the lights"})

    assert "brightness_pct" in captured["payload"]
    assert captured["payload"]["brightness_pct"] == 30
    assert "dim" in result.lower()


def test_smart_home_state_query_on():
    from backend.skills.smart_home import run

    def fake_get(url, *, timeout=6.0, **kw):
        return _make_resp({"state": "on", "entity_id": "light.all"})

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_get", side_effect=fake_get):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "is the light on"})

    assert "on" in result.lower()


def test_smart_home_state_query_off():
    from backend.skills.smart_home import run

    def fake_get(url, *, timeout=6.0, **kw):
        return _make_resp({"state": "off", "entity_id": "light.all"})

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_get", side_effect=fake_get):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "is the light on"})

    assert "off" in result.lower()


def test_smart_home_german_turn_on():
    from backend.skills.smart_home import run

    def fake_post(url, *, timeout=6.0, **kw):
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "schalte das licht ein", "language": "de"})

    assert "eingeschaltet" in result or "an" in result.lower()


def test_smart_home_german_turn_off():
    from backend.skills.smart_home import run

    def fake_post(url, *, timeout=6.0, **kw):
        return _make_resp([])

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=fake_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "licht aus", "language": "de"})

    assert "ausgeschaltet" in result or "aus" in result.lower()


def test_smart_home_api_failure_graceful():
    from backend.skills.smart_home import run

    def failing_post(url, *, timeout=6.0, **kw):
        raise ConnectionError("refused")

    with patch("backend.skills.smart_home.config") as cfg, \
         patch("backend.skills.smart_home.http_post", side_effect=failing_post):
        cfg.HA_TOKEN = "tok"
        cfg.HA_BASE_URL = "http://ha.local:8123"
        cfg.HA_LIGHT_ENTITY = "light.all"
        result = run({"utterance": "turn on the lights"})

    assert "couldn't" in result.lower() or "konnte" in result.lower()


def test_smart_home_self_test():
    from backend.skills.smart_home import self_test
    assert self_test()


def test_smart_home_config_keys():
    from backend.core.config import config
    assert hasattr(config, "HA_BASE_URL")
    assert hasattr(config, "HA_TOKEN")
    assert hasattr(config, "HA_LIGHT_ENTITY")


# ═══════════════════════════════════════════════════════════════════════════════
# Weather — mocked HTTP
# ═══════════════════════════════════════════════════════════════════════════════

_GEOCODE_RESP = {"results": [{"latitude": 51.5, "longitude": 6.6, "name": "Moers"}]}
_WEATHER_RESP = {
    "current": {
        "temperature_2m": 18.5,
        "weather_code": 1,
        "wind_speed_10m": 12.0,
    }
}


def test_weather_returns_formatted_string():
    from backend.skills.weather import run

    call_count = [0]

    def fake_get(url, *, timeout=6.0, **kw):
        call_count[0] += 1
        if "geocoding" in url:
            return _make_resp(_GEOCODE_RESP)
        return _make_resp(_WEATHER_RESP)

    with patch("backend.skills.weather.http_get", side_effect=fake_get):
        result = run({"utterance": "weather in Moers"})

    assert "Moers" in result
    assert "18" in result or "degrees" in result
    assert call_count[0] == 2  # geocode + weather


def test_weather_city_not_found():
    from backend.skills.weather import run

    def fake_get(url, *, timeout=6.0, **kw):
        if "geocoding" in url:
            return _make_resp({"results": []})
        return _make_resp(_WEATHER_RESP)

    with patch("backend.skills.weather.http_get", side_effect=fake_get):
        result = run({"utterance": "weather in Narnia"})

    assert "couldn't find" in result.lower() or "narnia" in result.lower()


def test_weather_api_failure_graceful():
    from backend.skills.weather import run

    def failing_get(url, *, timeout=6.0, **kw):
        raise ConnectionError("no network")

    with patch("backend.skills.weather.http_get", side_effect=failing_get):
        result = run({"utterance": "weather"})

    assert "couldn't" in result.lower() or "error" in result.lower()


def test_weather_defaults_to_moers():
    from backend.skills.weather import run
    captured = {}

    def fake_get(url, *, timeout=6.0, **kw):
        if "geocoding" in url:
            captured["city"] = kw.get("params", {}).get("name", "")
            return _make_resp(_GEOCODE_RESP)
        return _make_resp(_WEATHER_RESP)

    with patch("backend.skills.weather.http_get", side_effect=fake_get):
        run({"utterance": "what's the weather"})

    assert captured.get("city", "").lower() == "moers"


# ═══════════════════════════════════════════════════════════════════════════════
# Weather Forecast — mocked HTTP
# ═══════════════════════════════════════════════════════════════════════════════

_FORECAST_RESP = {
    "daily": {
        "time": ["2026-06-17", "2026-06-18", "2026-06-19", "2026-06-20", "2026-06-21"],
        "temperature_2m_max": [22.0, 24.0, 19.0, 20.0, 23.0],
        "temperature_2m_min": [14.0, 15.0, 11.0, 12.0, 13.0],
        "weather_code": [1, 61, 3, 0, 80],
    }
}


def test_forecast_returns_5_days():
    from backend.skills.weather_forecast import run

    def fake_get(url, *, timeout=6.0, **kw):
        if "geocoding" in url:
            return _make_resp(_GEOCODE_RESP)
        return _make_resp(_FORECAST_RESP)

    # weather_forecast calls _geocode (from weather.py) + its own http_get
    with patch("backend.skills.weather.http_get", side_effect=fake_get), \
         patch("backend.skills.weather_forecast.http_get", side_effect=fake_get):
        result = run({"utterance": "weather forecast"})

    assert "Today" in result
    assert "Tomorrow" in result
    assert "Moers" in result


def test_forecast_city_not_found():
    from backend.skills.weather_forecast import run

    def fake_get(url, *, timeout=6.0, **kw):
        if "geocoding" in url:
            return _make_resp({"results": []})
        return _make_resp(_FORECAST_RESP)

    with patch("backend.skills.weather.http_get", side_effect=fake_get), \
         patch("backend.skills.weather_forecast.http_get", side_effect=fake_get):
        result = run({"utterance": "forecast for Atlantis"})

    assert "couldn't find" in result.lower()


def test_forecast_api_failure_graceful():
    from backend.skills.weather_forecast import run

    def failing_get(url, *, timeout=6.0, **kw):
        raise ConnectionError("no network")

    with patch("backend.skills.weather.http_get", side_effect=failing_get), \
         patch("backend.skills.weather_forecast.http_get", side_effect=failing_get):
        result = run({"utterance": "weather forecast"})

    assert "couldn't" in result.lower()


def test_forecast_city_from_utterance():
    from backend.skills.weather_forecast import run
    captured = {}

    def fake_geo(url, *, timeout=6.0, **kw):
        captured["city"] = kw.get("params", {}).get("name", "")
        return _make_resp({"results": [{"latitude": 48.1, "longitude": 11.6, "name": "Munich"}]})

    def fake_forecast(url, *, timeout=6.0, **kw):
        return _make_resp(_FORECAST_RESP)

    with patch("backend.skills.weather.http_get", side_effect=fake_geo), \
         patch("backend.skills.weather_forecast.http_get", side_effect=fake_forecast):
        run({"utterance": "forecast for Munich"})

    assert captured.get("city", "").lower() == "munich"


# ═══════════════════════════════════════════════════════════════════════════════
# Translator — mocked HTTP + bug fixes
# ═══════════════════════════════════════════════════════════════════════════════

def test_translator_http_success():
    from backend.skills.translator import run

    def fake_get(url, *, timeout=6.0, **kw):
        return _make_resp({
            "responseData": {"translatedText": "Bonjour"},
        })

    with patch("backend.skills.translator.http_get", side_effect=fake_get):
        result = run({"utterance": "say hello in french"})

    assert "Bonjour" in result
    assert "french" in result.lower()


def test_translator_http_same_as_input_means_fail():
    """If translation == original phrase, we say we couldn't translate."""
    from backend.skills.translator import run

    def fake_get(url, *, timeout=6.0, **kw):
        return _make_resp({
            "responseData": {"translatedText": "hello"},
        })

    with patch("backend.skills.translator.http_get", side_effect=fake_get):
        result = run({"utterance": "say hello in french"})

    assert "couldn't" in result.lower()


def test_translator_http_error_graceful():
    from backend.skills.translator import run

    def failing_get(url, *, timeout=6.0, **kw):
        raise ConnectionError("offline")

    with patch("backend.skills.translator.http_get", side_effect=failing_get):
        result = run({"utterance": "say hello in french"})

    assert "couldn't" in result.lower() or "reach" in result.lower()


def test_translator_timeout_graceful():
    """TimeoutError should produce a friendly message, not NameError (bug fix)."""
    from backend.skills.translator import run
    import httpx

    def timeout_get(url, *, timeout=6.0, **kw):
        raise httpx.TimeoutException("timed out")

    with patch("backend.skills.translator.http_get", side_effect=timeout_get):
        result = run({"utterance": "say hello in french"})

    assert "too long" in result.lower() or "couldn't" in result.lower()


def test_translator_empty_translation_graceful():
    from backend.skills.translator import run

    def fake_get(url, *, timeout=6.0, **kw):
        return _make_resp({"responseData": {"translatedText": ""}})

    with patch("backend.skills.translator.http_get", side_effect=fake_get):
        result = run({"utterance": "say hello in french"})

    assert "couldn't" in result.lower()
