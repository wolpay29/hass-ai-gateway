import os

# Set env vars before any bot module is imported (config.py reads at module level)
os.environ.setdefault("BOT_TOKEN", "test_bot_token")
os.environ.setdefault("MY_CHAT_ID", "99999")
os.environ.setdefault("HA_URL", "http://homeassistant.test:8123")
os.environ.setdefault("HA_TOKEN", "test_ha_token_abc")
os.environ.setdefault("LMSTUDIO_URL", "http://lmstudio.test:1234")
os.environ.setdefault("LMSTUDIO_MODEL", "test-model")
os.environ.setdefault("LMSTUDIO_API_KEY", "")
os.environ.setdefault("FALLBACK_MODE", "0")
os.environ.setdefault("LLM_HISTORY_SIZE", "0")
os.environ.setdefault("MAX_ACTIONS_PER_COMMAND", "0")

# Pre-import bot modules so @patch("bot.ha.requests.post") can resolve them
import bot.ha   # noqa: E402, F401
import bot.llm  # noqa: E402, F401
