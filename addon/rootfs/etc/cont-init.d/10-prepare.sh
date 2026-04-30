#!/command/with-contenv bashio
# Prepare the persistent /data layout and warn on missing required config.
set -e

mkdir -p /data/voice /data/rag

bashio::log.info "hass-ai-gateway: data dir ready (/data/voice, /data/rag)"

# User-editable config files in /config (= /addon_configs/<slug>/ on the host,
# visible via Samba and the official "File editor" addon).
# Defaults are baked into the image; we only seed missing files so the user's
# edits survive addon updates.
USER_DIR=/config/userconfig
mkdir -p "${USER_DIR}"
for f in entities.yaml entities_blacklist.yaml pre_llm_memory.md post_llm_memory.md; do
    if [ ! -f "${USER_DIR}/${f}" ]; then
        cp "/opt/gateway/core/userconfig/${f}" "${USER_DIR}/${f}"
        bashio::log.info "seeded ${USER_DIR}/${f} from defaults"
    fi
done

if [ ! -f /config/menus.yaml ]; then
    cp /opt/gateway/services/telegram_bot/menus.yaml /config/menus.yaml
    bashio::log.info "seeded /config/menus.yaml from defaults"
fi

bashio::log.info "hass-ai-gateway: user config ready at /addon_configs/<slug>/"

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

bashio::log.info "hass-ai-gateway: cont-init complete"
