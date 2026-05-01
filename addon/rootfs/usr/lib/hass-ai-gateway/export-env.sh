#!/usr/bin/env bashio
# Source this from each /etc/services.d/*/run script after the bashio shebang.
# It maps /data/options.json keys -> the env vars core/config.py expects.
# Pure exports; no exec / no flow control.

# --- Telegram + HA ---
export BOT_TOKEN="$(bashio::config 'telegram.bot_token')"
export MY_CHAT_ID="$(bashio::config 'telegram.chat_id')"
export HA_URL="$(bashio::config 'home_assistant.url')"
export HA_TOKEN="$(bashio::config 'home_assistant.token')"
if [ -z "${HA_TOKEN}" ] || [ "${HA_TOKEN}" = "null" ]; then
    export HA_TOKEN="${SUPERVISOR_TOKEN:-}"
fi
export HA_SERVICE_TIMEOUT="$(bashio::config 'home_assistant.service_timeout')"
export HA_DRY_RUN="$(bashio::config 'home_assistant.dry_run')"

# --- Whisper (external only for v1.0) ---
export WHISPER_BACKEND=external
export WHISPER_EXTERNAL_URL="$(bashio::config 'whisper.external_url')"
export WHISPER_EXTERNAL_MODEL="$(bashio::config 'whisper.external_model')"
export WHISPER_LANGUAGE="$(bashio::config 'whisper.language')"

# --- LM Studio ---
export LMSTUDIO_URL="$(bashio::config 'lmstudio.url')"
export LMSTUDIO_MODEL="$(bashio::config 'lmstudio.model')"
export LMSTUDIO_API_KEY="$(bashio::config 'lmstudio.api_key')"
export LMSTUDIO_TIMEOUT="$(bashio::config 'lmstudio.timeout')"
export LMSTUDIO_TEMPERATURE="$(bashio::config 'lmstudio.temperature')"
export LMSTUDIO_NO_THINK="$(bashio::config 'lmstudio.no_think')"
export LMSTUDIO_CONTEXT_LENGTH="$(bashio::config 'lmstudio.context_length')"
export LMSTUDIO_MCP_ALLOWED_TOOLS="$(bashio::config 'lmstudio.mcp_allowed_tools')"
export MAX_ACTIONS_PER_COMMAND="$(bashio::config 'lmstudio.max_actions_per_command')"

# --- Voice Gateway ---
export GATEWAY_PORT="$(bashio::config 'voice_gateway.port')"
export GATEWAY_API_KEY="$(bashio::config 'voice_gateway.api_key')"
export GATEWAY_TELEGRAM_PUSH="$(bashio::config 'voice_gateway.telegram_push')"
export VOICE_REPLY_WITH_TRANSCRIPT="$(bashio::config 'voice_gateway.reply_with_transcript')"

# --- Notify Gateway ---
export NOTIFY_PORT="$(bashio::config 'notify_gateway.port')"
export NOTIFY_HTTP_TIMEOUT="$(bashio::config 'notify_gateway.http_timeout')"

# --- TTS ---
export TTS_EXTERNAL_URL="$(bashio::config 'tts.external_url')"
export TTS_EXTERNAL_VOICE="$(bashio::config 'tts.external_voice')"

# --- RAG ---
export RAG_ENABLED="$(bashio::config 'rag.enabled')"
export RAG_DB_PATH=/data/rag/entities.sqlite
export RAG_TOP_K="$(bashio::config 'rag.top_k')"
export RAG_DISTANCE_THRESHOLD="$(bashio::config 'rag.distance_threshold')"
export RAG_KEYWORD_BOOST="$(bashio::config 'rag.keyword_boost')"
export RAG_EMBED_URL="$(bashio::config 'rag.embed_url')"
export RAG_EMBED_MODEL="$(bashio::config 'rag.embed_model')"
export RAG_EMBED_DIM="$(bashio::config 'rag.embed_dim')"

# --- LLM Preprocessor ---
export LLM_PREPROCESSOR="$(bashio::config 'llm_preprocessor.enabled')"
export LLM_PREPROCESSOR_URL="$(bashio::config 'llm_preprocessor.url')"
export LLM_PREPROCESSOR_API_KEY="$(bashio::config 'llm_preprocessor.api_key')"
export LLM_PREPROCESSOR_MODEL="$(bashio::config 'llm_preprocessor.model')"
export LLM_PREPROCESSOR_TIMEOUT="$(bashio::config 'llm_preprocessor.timeout')"
export LLM_PREPROCESSOR_TEMPERATURE="$(bashio::config 'llm_preprocessor.temperature')"

# --- Fallback ---
export FALLBACK_MODE="$(bashio::config 'fallback.mode')"
export FALLBACK_REST_MAX_ENTITIES="$(bashio::config 'fallback.rest_max_entities')"
export FALLBACK_REST_DOMAINS="$(bashio::config 'fallback.rest_domains')"

# --- History (chat memory across turns) ---
export LLM_HISTORY_SIZE="$(bashio::config 'history.size')"
export HISTORY_INCLUDE_ASSISTANT="$(bashio::config 'history.include_assistant')"
export HISTORY_APPEND_EXECUTIONS="$(bashio::config 'history.append_executions')"

# --- Persistent paths ---
export VOICE_DOWNLOAD_DIR=/data/voice
export PYTHONPATH=/opt/gateway

# --- User-editable config (mapped to /addon_configs/<slug>/ on the host) ---
export USERCONFIG_DIR=/config/userconfig
export TELEGRAM_MENUS_PATH=/config/menus.yaml
