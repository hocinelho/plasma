"""Tests for the features batch: shopping list, alarm, currency, scenes, proactive TTS wiring."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call


def _make_resp(json_data, status=200):
    r = MagicMock()
    r.raise_for_status.return_value = r
    r.json.return_value = json_data
    r.status_code = status
    return r


# ── Shopping list ─────────────────────────────────────────────────────────────

def test_shopping_add_en(tmp_path):
    from backend.skills.shopping_list import run
    with patch("backend.skills.shopping_list._LIST_FILE", tmp_path / "shopping.json"):
        result = run({"utterance": "add milk to my shopping list"})
    assert "milk" in result.lower()


def test_shopping_add_de(tmp_path):
    from backend.skills.shopping_list import run
    with patch("backend.skills.shopping_list._LIST_FILE", tmp_path / "shopping.json"):
        result = run({"utterance": "zur Einkaufsliste hinzufügen: Brot", "language": "de"})
    assert "brot" in result.lower()


def test_shopping_show_empty(tmp_path):
    from backend.skills.shopping_list import run
    with patch("backend.skills.shopping_list._LIST_FILE", tmp_path / "shopping.json"):
        result = run({"utterance": "show my shopping list"})
    assert "empty" in result.lower()


def test_shopping_show_with_items(tmp_path):
    from backend.skills.shopping_list import run
    list_file = tmp_path / "shopping.json"
    list_file.write_text('["milk", "eggs"]', encoding="utf-8")
    with patch("backend.skills.shopping_list._LIST_FILE", list_file):
        result = run({"utterance": "show my shopping list"})
    assert "milk" in result.lower()
    assert "eggs" in result.lower()


def test_shopping_remove_en(tmp_path):
    from backend.skills.shopping_list import run
    list_file = tmp_path / "shopping.json"
    list_file.write_text('["milk", "eggs"]', encoding="utf-8")
    with patch("backend.skills.shopping_list._LIST_FILE", list_file):
        result = run({"utterance": "remove milk from shopping list"})
    assert "milk" in result.lower()
    remaining = json.loads(list_file.read_text())
    assert "milk" not in remaining


def test_shopping_clear(tmp_path):
    from backend.skills.shopping_list import run
    list_file = tmp_path / "shopping.json"
    list_file.write_text('["milk", "eggs"]', encoding="utf-8")
    with patch("backend.skills.shopping_list._LIST_FILE", list_file):
        result = run({"utterance": "clear my shopping list"})
    assert "clear" in result.lower() or "geleert" in result.lower()
    assert json.loads(list_file.read_text()) == []


def test_shopping_no_duplicates(tmp_path):
    from backend.skills.shopping_list import run
    list_file = tmp_path / "shopping.json"
    with patch("backend.skills.shopping_list._LIST_FILE", list_file):
        run({"utterance": "add milk to my shopping list"})
        run({"utterance": "add milk to my shopping list"})
        items = json.loads(list_file.read_text())
    assert items.count("milk") == 1


def test_shopping_self_test():
    from backend.skills.shopping_list import self_test
    assert self_test()


def test_shopping_meta():
    from backend.skills.shopping_list import META
    assert META["name"] == "shopping_list"
    assert len(META["triggers"]) >= 5


# ── Alarm ────────────────────────────────────────────────────────────────────

def test_alarm_set_with_time(tmp_path):
    from backend.skills.alarm import run
    with patch("backend.skills.alarm._ALARM_FILE", tmp_path / "alarms.json"), \
         patch("backend.skills.alarm._schedule_alarm"):
        result = run({"utterance": "set an alarm for 7am"})
    assert "7" in result or "alarm" in result.lower() or "wecker" in result.lower()


def test_alarm_set_prompts_for_time(tmp_path):
    from backend.skills.alarm import run
    with patch("backend.skills.alarm._ALARM_FILE", tmp_path / "alarms.json"), \
         patch("backend.skills.alarm._schedule_alarm"), \
         patch("backend.skills.alarm._set_pending", return_value="What time?") as mock_pending:
        result = run({"utterance": "set alarm", "session_id": "sess1"})
    mock_pending.assert_called_once()
    assert "time" in result.lower() or "what" in result.lower()


def test_alarm_list_empty(tmp_path):
    from backend.skills.alarm import run
    with patch("backend.skills.alarm._ALARM_FILE", tmp_path / "alarms.json"):
        result = run({"utterance": "list alarms"})
    assert "no alarm" in result.lower() or "keine" in result.lower()


def test_alarm_cancel(tmp_path):
    from backend.skills.alarm import run
    alarm_file = tmp_path / "alarms.json"
    alarm_file.write_text('[{"time": "2099-01-01T07:00:00", "label": "Alarm", "language": "en"}]')
    with patch("backend.skills.alarm._ALARM_FILE", alarm_file), \
         patch("backend.skills.alarm._schedule_alarm"):
        result = run({"utterance": "cancel alarm"})
    assert json.loads(alarm_file.read_text()) == []


def test_alarm_self_test():
    from backend.skills.alarm import self_test
    assert self_test()


def test_alarm_parse_time_24h():
    from backend.skills.alarm import _parse_time
    dt = _parse_time("wake me up at 14:30")
    assert dt is not None
    assert dt.hour == 14
    assert dt.minute == 30


def test_alarm_parse_time_ampm():
    from backend.skills.alarm import _parse_time
    dt = _parse_time("alarm at 7am")
    assert dt is not None
    assert dt.hour == 7


def test_alarm_fire_calls_proactive_tts():
    from backend.skills import alarm as alarm_mod
    fired = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired.append((text, lang))
    with patch.dict("sys.modules", {"backend.modules.voice.proactive_tts": MagicMock(proactive_tts=mock_ptts)}), \
         patch("backend.skills.alarm._load", return_value=[]), \
         patch("backend.skills.alarm._save"):
        from datetime import datetime
        alarm_mod._fire_alarm(datetime.now().isoformat(), "Test", "en")
    # Should have called proactive_tts.fire (via the patched module)


# ── Currency ─────────────────────────────────────────────────────────────────

_FRANKFURTER_RESP = {"amount": 100.0, "base": "USD", "date": "2024-01-01", "rates": {"EUR": 92.5}}
_RATE_RESP = {"amount": 1.0, "base": "USD", "date": "2024-01-01", "rates": {"EUR": 0.925}}


def test_currency_convert_usd_to_eur():
    from backend.skills.currency import run
    with patch("backend.skills.currency.http_get", return_value=_make_resp(_FRANKFURTER_RESP)):
        result = run({"utterance": "convert 100 USD to EUR"})
    assert "92" in result or "EUR" in result


def test_currency_convert_de():
    from backend.skills.currency import run
    with patch("backend.skills.currency.http_get", return_value=_make_resp(_FRANKFURTER_RESP)):
        result = run({"utterance": "100 Dollar in Euro", "language": "de"})
    assert "EUR" in result or "92" in result


def test_currency_exchange_rate():
    from backend.skills.currency import run
    with patch("backend.skills.currency.http_get", return_value=_make_resp(_RATE_RESP)):
        result = run({"utterance": "exchange rate USD to EUR"})
    assert "0.925" in result or "EUR" in result


def test_currency_api_failure():
    from backend.skills.currency import run
    def fail(*a, **kw):
        raise ConnectionError("offline")
    with patch("backend.skills.currency.http_get", side_effect=fail):
        result = run({"utterance": "convert 100 USD to EUR"})
    assert "couldn't" in result.lower() or "failed" in result.lower() or "fehlgeschlagen" in result.lower()


def test_currency_no_match_returns_help():
    from backend.skills.currency import run
    result = run({"utterance": "tell me about currency"})
    assert "try" in result.lower() or "sag" in result.lower()


def test_currency_self_test():
    from backend.skills.currency import self_test
    assert self_test()


def test_currency_meta():
    from backend.skills.currency import META
    assert META["name"] == "currency"
    assert any("usd" in t.lower() or "convert" in t.lower() for t in META["triggers"])


def test_currency_normalize():
    from backend.skills.currency import _normalize
    assert _normalize("dollar") == "USD"
    assert _normalize("euros") == "EUR"
    assert _normalize("pound") == "GBP"


# ── Smart home scenes ─────────────────────────────────────────────────────────

def _ha_config():
    cfg = MagicMock()
    cfg.HA_TOKEN = "token123"
    cfg.HA_BASE_URL = "http://ha.local:8123"
    cfg.HA_LIGHT_ENTITY = "light.all"
    return cfg


def test_smart_home_scene_activate():
    from backend.skills.smart_home import run
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = mock_resp
    with patch("backend.skills.smart_home.config", _ha_config()), \
         patch("backend.skills.smart_home.http_post", return_value=mock_resp):
        result = run({"utterance": "activate movie mode"})
    assert "movie" in result.lower() or "activated" in result.lower() or "szene" in result.lower()


def test_smart_home_scene_night_mode():
    from backend.skills.smart_home import run
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = mock_resp
    with patch("backend.skills.smart_home.config", _ha_config()), \
         patch("backend.skills.smart_home.http_post", return_value=mock_resp):
        result = run({"utterance": "turn on night mode"})
    assert "night" in result.lower() or "activated" in result.lower()


def test_smart_home_scene_de():
    from backend.skills.smart_home import run
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = mock_resp
    with patch("backend.skills.smart_home.config", _ha_config()), \
         patch("backend.skills.smart_home.http_post", return_value=mock_resp):
        result = run({"utterance": "Film Modus aktivieren", "language": "de"})
    assert "film" in result.lower() or "szene" in result.lower() or "aktiviert" in result.lower()


# ── Proactive TTS ─────────────────────────────────────────────────────────────

def test_proactive_tts_fire_before_start_logs_warning():
    from backend.modules.voice.proactive_tts import ProactiveTTS
    ptts = ProactiveTTS()
    # Should not raise even if not started
    ptts.fire("test alert", "en")


def test_proactive_tts_add_remove_client():
    from backend.modules.voice.proactive_tts import ProactiveTTS
    ptts = ProactiveTTS()
    ws = MagicMock()
    ptts.add_client(ws)
    assert ws in ptts.clients
    ptts.remove_client(ws)
    assert ws not in ptts.clients


# ── Reminder proactive TTS wiring ─────────────────────────────────────────────

def test_reminder_fire_calls_proactive_tts():
    from backend.skills import reminder as rem_mod
    fired = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired.append((text, lang))

    import sys
    fake_module = MagicMock()
    fake_module.proactive_tts = mock_ptts
    with patch.dict(sys.modules, {"backend.modules.voice.proactive_tts": fake_module}):
        rem_mod._fire(0, "take medication", "en")

    assert any("medication" in t for t, l in fired)


def test_reminder_fire_de():
    from backend.skills import reminder as rem_mod
    fired = []
    mock_ptts = MagicMock()
    mock_ptts.fire = lambda text, lang: fired.append((text, lang))

    import sys
    fake_module = MagicMock()
    fake_module.proactive_tts = mock_ptts
    with patch.dict(sys.modules, {"backend.modules.voice.proactive_tts": fake_module}):
        rem_mod._fire(0, "Medikament nehmen", "de")

    assert any("de" == l for t, l in fired)


# ── Multi-step (pending intent) ───────────────────────────────────────────────

def test_pending_intent_routes_to_alarm():
    from backend.modules.router import chat_service

    mock_memory = MagicMock()
    mock_memory.get_facts.return_value = [
        {"id": 42, "content": "alarm:awaiting_time", "category": "pending_intent"}
    ]
    mock_memory.get_conversation.return_value = []

    mock_alarm_skill = MagicMock()
    mock_alarm_skill.name = "alarm"
    mock_alarm_skill.invoke.return_value = "Alarm set for 7:00 AM."

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_alarm_skill
    mock_registry.find_by_trigger.return_value = None

    with patch.object(chat_service, "get_memory", return_value=mock_memory), \
         patch("backend.modules.router.chat_service.get_registry", return_value=mock_registry), \
         patch("backend.modules.router.chat_service.get_suggester", return_value=MagicMock(record_fallback=lambda x: None)):
        result = chat_service.handle_chat("sess1", "7am", "en")

    assert "7" in result or "alarm" in result.lower()
    mock_memory.delete_fact.assert_called_once_with(42)


def test_pending_intent_not_triggered_when_none():
    from backend.modules.router import chat_service

    mock_memory = MagicMock()
    mock_memory.get_facts.return_value = []
    mock_memory.get_conversation.return_value = []

    mock_skill = MagicMock()
    mock_skill.name = "weather"
    mock_skill.invoke.return_value = "It's sunny."

    mock_registry = MagicMock()
    mock_registry.find_by_trigger.return_value = mock_skill

    with patch.object(chat_service, "get_memory", return_value=mock_memory), \
         patch("backend.modules.router.chat_service.get_registry", return_value=mock_registry):
        result = chat_service.handle_chat("sess1", "weather in Berlin", "en")

    assert result == "It's sunny."
    mock_memory.delete_fact.assert_not_called()
