"""Tests for bot/llm.py — all HTTP calls and file I/O are mocked."""
import json
import pytest
from unittest.mock import patch, MagicMock

import bot.llm
from bot.llm import (
    _lmstudio_headers, _format_state_simple,
    parse_command, parse_command_with_states, format_state_reply,
)


ENTITIES_YAML = """
entities:
  - id: light.licht_paul
    description: "Licht Zimmer Paul"
    keywords: ["paul"]
    actions: ["turn_on", "turn_off", "get_state"]
    domain: light
  - id: switch.pool_pump
    description: "Pool Pumpe"
    keywords: ["pool", "pumpe"]
    actions: ["turn_on", "turn_off"]
    domain: switch
"""


def _make_llm_response(content: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content, "reasoning_content": None}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# _lmstudio_headers
# ---------------------------------------------------------------------------

class TestLmstudioHeaders:
    def test_no_auth_header_when_key_empty(self):
        with patch("bot.llm.LMSTUDIO_API_KEY", ""):
            headers = _lmstudio_headers()
            assert "Authorization" not in headers
            assert headers["Content-Type"] == "application/json"

    def test_bearer_token_when_key_set(self):
        with patch("bot.llm.LMSTUDIO_API_KEY", "my-secret-key"):
            headers = _lmstudio_headers()
            assert headers["Authorization"] == "Bearer my-secret-key"


# ---------------------------------------------------------------------------
# _format_state_simple
# ---------------------------------------------------------------------------

class TestFormatStateSimple:
    def test_formats_on_state(self):
        data = [{"entity_id": "light.licht_paul", "description": "Licht Paul",
                 "ha_response": {"state": "on", "attributes": {}}}]
        result = _format_state_simple(data)
        assert "Licht Paul" in result
        assert "an" in result

    def test_formats_off_state(self):
        data = [{"entity_id": "switch.pool_pump", "description": "Pool Pumpe",
                 "ha_response": {"state": "off", "attributes": {}}}]
        result = _format_state_simple(data)
        assert "aus" in result

    def test_formats_numeric_with_unit(self):
        data = [{"entity_id": "sensor.temp", "description": "Temperatur",
                 "ha_response": {"state": "24.5", "attributes": {"unit_of_measurement": "°C"}}}]
        result = _format_state_simple(data)
        assert "24.5" in result
        assert "°C" in result

    def test_handles_none_ha_response(self):
        data = [{"entity_id": "sensor.temp", "description": "Temperatur", "ha_response": None}]
        result = _format_state_simple(data)
        assert "nicht verfügbar" in result

    def test_uses_entity_id_when_no_description(self):
        data = [{"entity_id": "sensor.temp",
                 "ha_response": {"state": "22", "attributes": {}}}]
        result = _format_state_simple(data)
        assert "sensor.temp" in result


# ---------------------------------------------------------------------------
# parse_command
# ---------------------------------------------------------------------------

class TestParseCommand:
    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_returns_valid_action(self, _mock_read, mock_post):
        payload = json.dumps({
            "reply": "Schalte Licht Paul ein.",
            "actions": [{"entity_id": "light.licht_paul", "action": "turn_on", "domain": "light"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command("Licht Paul einschalten")
        assert result is not None
        assert result["actions"][0]["entity_id"] == "light.licht_paul"

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_filters_hallucinated_entity(self, _mock_read, mock_post):
        payload = json.dumps({
            "reply": "OK",
            "actions": [{"entity_id": "light.does_not_exist", "action": "turn_on", "domain": "light"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command("Phantom einschalten")
        assert result is not None
        assert result["actions"] == []

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_allows_needs_fallback_action(self, _mock_read, mock_post):
        payload = json.dumps({
            "reply": "Nicht möglich",
            "actions": [{"entity_id": "light.licht_paul", "action": "needs_fallback", "domain": "light"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command("Licht auf 50% dimmen")
        assert result["actions"][0]["action"] == "needs_fallback"

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_returns_none_when_no_json_in_response(self, _mock_read, mock_post):
        mock_post.return_value = _make_llm_response("Ich bin ein Sprachmodell und kann nicht helfen.")
        result = parse_command("irgendwas")
        assert result is None

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_returns_none_on_http_error(self, _mock_read, mock_post):
        import requests as req
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=req.exceptions.HTTPError("503")),
            text="Service Unavailable"
        )
        result = parse_command("Licht an")
        assert result is None

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_returns_none_on_connection_error(self, _mock_read, mock_post):
        mock_post.side_effect = ConnectionError("no route to host")
        result = parse_command("Licht an")
        assert result is None

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_max_actions_limit_marks_excess_as_ignored(self, _mock_read, mock_post):
        payload = json.dumps({
            "reply": "Alles an.",
            "actions": [
                {"entity_id": "light.licht_paul", "action": "turn_on", "domain": "light"},
                {"entity_id": "switch.pool_pump", "action": "turn_on", "domain": "switch"},
            ]
        })
        mock_post.return_value = _make_llm_response(payload)
        with patch("bot.llm.MAX_ACTIONS_PER_COMMAND", 1):
            result = parse_command("Alles einschalten")
        assert result["actions"][1].get("ignored") is True

    @patch("bot.llm.requests.post")
    @patch("bot.llm.Path.read_text", return_value=ENTITIES_YAML)
    def test_empty_actions_list_returned_when_no_match(self, _mock_read, mock_post):
        payload = json.dumps({"reply": "Kein passendes Gerät gefunden.", "actions": []})
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command("Backofen einschalten")
        assert result["actions"] == []


# ---------------------------------------------------------------------------
# parse_command_with_states
# ---------------------------------------------------------------------------

class TestParseCommandWithStates:
    _states = [
        {"entity_id": "light.licht_paul", "domain": "light", "state": "off",
         "friendly_name": "Licht Paul", "unit": ""},
    ]

    @patch("bot.llm.requests.post")
    def test_returns_action_with_live_states(self, mock_post):
        payload = json.dumps({
            "reply": "Licht Paul an.",
            "actions": [{"entity_id": "light.licht_paul", "action": "turn_on", "domain": "light"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command_with_states("Licht Paul an", self._states)
        assert result["actions"][0]["entity_id"] == "light.licht_paul"

    @patch("bot.llm.requests.post")
    def test_returns_none_for_empty_states(self, mock_post):
        result = parse_command_with_states("Licht an", [])
        assert result is None
        mock_post.assert_not_called()

    @patch("bot.llm.requests.post")
    def test_filters_hallucinated_entity(self, mock_post):
        payload = json.dumps({
            "reply": "OK",
            "actions": [{"entity_id": "light.phantom", "action": "turn_on", "domain": "light"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command_with_states("Phantom an", self._states)
        assert result["actions"] == []

    @patch("bot.llm.requests.post")
    def test_infers_domain_from_entity_id(self, mock_post):
        payload = json.dumps({
            "reply": "OK",
            "actions": [{"entity_id": "light.licht_paul", "action": "turn_on"}]
        })
        mock_post.return_value = _make_llm_response(payload)
        result = parse_command_with_states("Licht an", self._states)
        assert result["actions"][0]["domain"] == "light"


# ---------------------------------------------------------------------------
# format_state_reply
# ---------------------------------------------------------------------------

class TestFormatStateReply:
    _state_data = [
        {"entity_id": "sensor.temp_pool", "description": "Pool Temperatur",
         "ha_response": {"state": "26.5", "attributes": {"unit_of_measurement": "°C"}}}
    ]

    @patch("bot.llm.requests.post")
    def test_returns_llm_antwort(self, mock_post):
        payload = json.dumps({"antwort": "Der Pool hat 26.5°C."})
        mock_post.return_value = _make_llm_response(payload)
        result = format_state_reply("Wie warm ist der Pool?", self._state_data)
        assert "26.5" in result

    @patch("bot.llm.requests.post")
    def test_falls_back_to_simple_format_on_empty_content(self, mock_post):
        mock_post.return_value = _make_llm_response("")
        result = format_state_reply("Wie warm ist der Pool?", self._state_data)
        assert "26.5" in result  # programmatic fallback

    @patch("bot.llm.requests.post")
    def test_falls_back_on_connection_error(self, mock_post):
        mock_post.side_effect = ConnectionError("no route")
        result = format_state_reply("Wie warm ist der Pool?", self._state_data)
        assert "26.5" in result

    def test_returns_empty_string_for_no_data(self):
        result = format_state_reply("Etwas?", [])
        assert result == ""
