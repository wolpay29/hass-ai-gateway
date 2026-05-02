#!/usr/bin/env bashio
# Source this from each /etc/services.d/*/run script after the bashio shebang.
# It maps /data/options.json keys -> the env vars core/config.py expects.
# Pure exports; no exec / no flow control.

# --- Language (UI strings + LLM prompts + Whisper transcription language) ---
export LANGUAGE="$(bashio::config 'language')"

# --- Telegram + HA ---
export BOT_TOKEN="$(bashio::config 'telegram_bot_token')"
export MY_CHAT_ID="$(bashio::config 'telegram_chat_id')"
export HA_URL="$(bashio::config 'ha_url')"
export HA_TOKEN="$(bashio::config 'ha_token')"
if [ -z "${HA_TOKEN}" ] || [ "${HA_TOKEN}" = "null" ]; then
    export HA_TOKEN="${SUPERVISOR_TOKEN:-}"
fi
export HA_SERVICE_TIMEOUT="$(bashio::config 'ha_service_timeout')"
export HA_DRY_RUN="$(bashio::config 'ha_dry_run')"

# --- Whisper (external only) ---
export WHISPER_EXTERNAL_URL="$(bashio::config 'whisper_url')"
export WHISPER_EXTERNAL_MODEL="$(bashio::config 'whisper_model')"

# --- LM Studio ---
export LMSTUDIO_URL="$(bashio::config 'lmstudio_url')"
export LMSTUDIO_MODEL="$(bashio::config 'lmstudio_model')"
export LMSTUDIO_API_KEY="$(bashio::config 'lmstudio_api_key')"
export LMSTUDIO_TIMEOUT="$(bashio::config 'lmstudio_timeout')"
export LMSTUDIO_TEMPERATURE="$(bashio::config 'lmstudio_temperature')"
export LMSTUDIO_NO_THINK="$(bashio::config 'lmstudio_no_think')"
export LMSTUDIO_CONTEXT_LENGTH="$(bashio::config 'lmstudio_context_length')"
export LMSTUDIO_MCP_ALLOWED_TOOLS="$(bashio::config 'lmstudio_mcp_allowed_tools')"
export MAX_ACTIONS_PER_COMMAND="$(bashio::config 'lmstudio_max_actions_per_command')"

# --- Voice Gateway ---
export GATEWAY_PORT="$(bashio::config 'voice_port')"
export GATEWAY_API_KEY="$(bashio::config 'voice_api_key')"
export GATEWAY_TELEGRAM_PUSH="$(bashio::config 'voice_telegram_push')"
export VOICE_REPLY_WITH_TRANSCRIPT="$(bashio::config 'voice_reply_with_transcript')"

# --- Notify Gateway ---
export NOTIFY_PORT="$(bashio::config 'notify_port')"
export NOTIFY_HTTP_TIMEOUT="$(bashio::config 'notify_http_timeout')"

# --- TTS ---
export TTS_EXTERNAL_URL="$(bashio::config 'tts_url')"
export TTS_EXTERNAL_VOICE="$(bashio::config 'tts_voice')"

# --- RAG ---
export RAG_ENABLED="$(bashio::config 'rag_enabled')"
export RAG_DB_PATH=/data/rag/entities.sqlite
export RAG_TOP_K="$(bashio::config 'rag_top_k')"
export RAG_DISTANCE_THRESHOLD="$(bashio::config 'rag_distance_threshold')"
export RAG_KEYWORD_BOOST="$(bashio::config 'rag_keyword_boost')"
export RAG_EMBED_URL="$(bashio::config 'rag_embed_url')"
export RAG_EMBED_MODEL="$(bashio::config 'rag_embed_model')"
export RAG_EMBED_DIM="$(bashio::config 'rag_embed_dim')"

# --- LLM Preprocessor ---
export LLM_PREPROCESSOR="$(bashio::config 'preprocessor_enabled')"
export LLM_PREPROCESSOR_URL="$(bashio::config 'preprocessor_url')"
export LLM_PREPROCESSOR_API_KEY="$(bashio::config 'preprocessor_api_key')"
export LLM_PREPROCESSOR_MODEL="$(bashio::config 'preprocessor_model')"
export LLM_PREPROCESSOR_TIMEOUT="$(bashio::config 'preprocessor_timeout')"
export LLM_PREPROCESSOR_TEMPERATURE="$(bashio::config 'preprocessor_temperature')"

# --- Fallback ---
export FALLBACK_MODE="$(bashio::config 'fallback_mode')"
export FALLBACK_REST_MAX_ENTITIES="$(bashio::config 'fallback_rest_max_entities')"
export FALLBACK_REST_DOMAINS="$(bashio::config 'fallback_rest_domains')"

# --- History (chat memory across turns) ---
export LLM_HISTORY_SIZE="$(bashio::config 'history_size')"
export HISTORY_INCLUDE_ASSISTANT="$(bashio::config 'history_include_assistant')"
export HISTORY_APPEND_EXECUTIONS="$(bashio::config 'history_append_executions')"

# --- Persistent paths ---
export VOICE_DOWNLOAD_DIR=/data/voice
export PYTHONPATH=/opt/gateway

# --- User-editable config (mapped to /addon_configs/<slug>/ on the host) ---
export USERCONFIG_DIR=/config/userconfig
export TELEGRAM_MENUS_PATH=/config/menus.yaml
