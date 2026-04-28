#!/command/with-contenv bashio
# Prepare the persistent /data layout and warn on missing required config.
set -e

mkdir -p /data/voice /data/rag

bashio::log.info "smarthome-assistant: data dir ready (/data/voice, /data/rag)"

if bashio::config.true 'services.telegram_bot'; then
    if ! bashio::config.has_value 'telegram.bot_token'; then
        bashio::log.warning "telegram_bot enabled but telegram.bot_token is empty"
    fi
    if [ "$(bashio::config 'telegram.chat_id')" = "0" ]; then
        bashio::log.warning "telegram_bot enabled but telegram.chat_id is 0"
    fi
fi

if bashio::config.true 'services.voice_gateway' || bashio::config.true 'services.telegram_bot'; then
    if ! bashio::config.has_value 'lmstudio.url'; then
        bashio::log.warning "lmstudio.url is empty — LLM-dependent commands will fail"
    fi
fi

bashio::log.info "smarthome-assistant: cont-init complete"
