"""Tests for bot/config.py — verifies env var loading and defaults."""
import bot.config as config


class TestConfigDefaults:
    def test_ha_url_loaded(self):
        assert config.HA_URL is not None
        assert config.HA_URL.startswith("http")

    def test_ha_token_loaded(self):
        assert config.HA_TOKEN is not None

    def test_lmstudio_url_loaded(self):
        assert config.LMSTUDIO_URL is not None
        assert config.LMSTUDIO_URL.startswith("http")

    def test_check_interval_is_int(self):
        assert isinstance(config.CHECK_INTERVAL_SECONDS, int)
        assert config.CHECK_INTERVAL_SECONDS > 0

    def test_battery_threshold_is_float(self):
        assert isinstance(config.BATTERY_THRESHOLD, float)

    def test_fallback_mode_is_int(self):
        assert isinstance(config.FALLBACK_MODE, int)
        assert config.FALLBACK_MODE in (0, 1, 2)

    def test_fallback_rest_domains_is_list(self):
        assert isinstance(config.FALLBACK_REST_DOMAINS, list)

    def test_mcp_allowed_tools_is_list(self):
        assert isinstance(config.LMSTUDIO_MCP_ALLOWED_TOOLS, list)

    def test_lmstudio_temperature_is_float(self):
        assert isinstance(config.LMSTUDIO_TEMPERATURE, float)
        assert 0.0 <= config.LMSTUDIO_TEMPERATURE <= 2.0

    def test_whisper_backend_is_valid(self):
        assert config.WHISPER_BACKEND in ("local", "external")

    def test_lmstudio_timeout_is_positive_int(self):
        assert isinstance(config.LMSTUDIO_TIMEOUT, int)
        assert config.LMSTUDIO_TIMEOUT > 0

    def test_my_chat_id_is_int(self):
        assert isinstance(config.MY_CHAT_ID, int)
