"""Tests for bot/ha.py — all HTTP calls are mocked."""
import pytest
from unittest.mock import patch, MagicMock

import bot.ha
from bot.ha import (
    call_service, get_state, get_ha_state, get_all_states, trigger_automation
)


# ---------------------------------------------------------------------------
# call_service
# ---------------------------------------------------------------------------

class TestCallService:
    def _make_response(self, status_code):
        r = MagicMock()
        r.status_code = status_code
        return r

    @patch("bot.ha.requests.post")
    def test_returns_true_on_200(self, mock_post):
        mock_post.return_value = self._make_response(200)
        assert call_service("light", "turn_on", "light.licht_paul") is True

    @patch("bot.ha.requests.post")
    def test_returns_true_on_201(self, mock_post):
        mock_post.return_value = self._make_response(201)
        assert call_service("switch", "turn_off", "switch.pool_pump") is True

    @patch("bot.ha.requests.post")
    def test_returns_false_on_non_200(self, mock_post):
        mock_post.return_value = self._make_response(401)
        assert call_service("light", "turn_on", "light.licht_paul") is False

    @patch("bot.ha.requests.post")
    def test_returns_false_on_exception(self, mock_post):
        mock_post.side_effect = ConnectionError("unreachable")
        assert call_service("light", "turn_on", "light.licht_paul") is False

    @patch("bot.ha.requests.post")
    def test_uses_trigger_action_for_automations(self, mock_post):
        mock_post.return_value = self._make_response(200)
        call_service("automation", "trigger", "automation.gate_open")
        url_called = mock_post.call_args[0][0]
        assert url_called.endswith("/api/services/automation/trigger")

    @patch("bot.ha.requests.post")
    def test_sends_correct_entity_id_in_body(self, mock_post):
        mock_post.return_value = self._make_response(200)
        call_service("light", "turn_on", "light.licht_paul")
        body = mock_post.call_args[1]["json"]
        assert body["entity_id"] == "light.licht_paul"


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------

class TestGetState:
    @patch("bot.ha.requests.get")
    def test_returns_dict_on_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"entity_id": "light.licht_paul", "state": "on", "attributes": {}}
        )
        result = get_state("light.licht_paul")
        assert result is not None
        assert result["state"] == "on"

    @patch("bot.ha.requests.get")
    def test_returns_none_on_404(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        assert get_state("light.does_not_exist") is None

    @patch("bot.ha.requests.get")
    def test_returns_none_on_exception(self, mock_get):
        mock_get.side_effect = ConnectionError("no connection")
        assert get_state("light.licht_paul") is None


# ---------------------------------------------------------------------------
# get_ha_state
# ---------------------------------------------------------------------------

class TestGetHaState:
    @patch("bot.ha.get_state")
    def test_returns_state_string(self, mock_get_state):
        mock_get_state.return_value = {"state": "on", "attributes": {}}
        assert get_ha_state("light.licht_paul") == "on"

    @patch("bot.ha.get_state")
    def test_returns_none_when_get_state_returns_none(self, mock_get_state):
        mock_get_state.return_value = None
        assert get_ha_state("light.licht_paul") is None


# ---------------------------------------------------------------------------
# get_all_states
# ---------------------------------------------------------------------------

class TestGetAllStates:
    _sample_states = [
        {"entity_id": "light.licht_paul", "state": "on", "attributes": {"friendly_name": "Licht Paul"}},
        {"entity_id": "switch.pool_pump", "state": "off", "attributes": {}},
        {"entity_id": "sensor.temp_pool", "state": "24.5", "attributes": {"unit_of_measurement": "°C"}},
        {"entity_id": "badformat", "state": "x", "attributes": {}},  # no dot → skipped
    ]

    @patch("bot.ha.requests.get")
    def test_returns_list_of_dicts(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._sample_states)
        result = get_all_states()
        assert isinstance(result, list)
        assert len(result) == 3  # badformat entry is skipped

    @patch("bot.ha.requests.get")
    def test_domain_filter_works(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._sample_states)
        result = get_all_states(domains=["light"])
        assert all(e["domain"] == "light" for e in result)
        assert len(result) == 1

    @patch("bot.ha.requests.get")
    def test_max_entities_limit(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._sample_states)
        result = get_all_states(max_entities=1)
        assert len(result) == 1

    @patch("bot.ha.requests.get")
    def test_returns_empty_list_on_non_200(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        assert get_all_states() == []

    @patch("bot.ha.requests.get")
    def test_returns_empty_list_on_exception(self, mock_get):
        mock_get.side_effect = ConnectionError("unreachable")
        assert get_all_states() == []

    @patch("bot.ha.requests.get")
    def test_result_contains_expected_keys(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._sample_states)
        result = get_all_states()
        for item in result:
            assert "entity_id" in item
            assert "state" in item
            assert "domain" in item


# ---------------------------------------------------------------------------
# trigger_automation
# ---------------------------------------------------------------------------

class TestTriggerAutomation:
    @patch("bot.ha.call_service")
    def test_delegates_to_call_service(self, mock_call):
        mock_call.return_value = True
        result = trigger_automation("automation.gate_open")
        mock_call.assert_called_once_with("automation", "trigger", "automation.gate_open")
        assert result is True
