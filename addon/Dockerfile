ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/gateway \
    WHISPER_BACKEND=external

# Runtime + build dependencies. Build deps are dropped at end of layer.
RUN apk add --no-cache \
        ffmpeg \
        ca-certificates \
        tzdata \
 && apk add --no-cache --virtual .build-deps \
        gcc \
        g++ \
        musl-dev \
        python3-dev \
        linux-headers \
        libffi-dev

WORKDIR /opt/gateway

# Stage gateway sources (populated by build-local.sh or CI before docker build).
COPY _build/core/                       /opt/gateway/core/
COPY _build/services/voice_gateway/     /opt/gateway/services/voice_gateway/
COPY _build/services/notify_gateway/    /opt/gateway/services/notify_gateway/
COPY _build/services/telegram_bot/      /opt/gateway/services/telegram_bot/

# Install Python deps. faster-whisper/ctranslate2 excluded (WHISPER_BACKEND=external).
RUN set -e \
 && grep -v -E '^[[:space:]]*faster-whisper' \
        /opt/gateway/services/voice_gateway/requirements.txt  > /tmp/req-vg.txt \
 && grep -v -E '^[[:space:]]*faster-whisper' \
        /opt/gateway/services/notify_gateway/requirements.txt > /tmp/req-ng.txt \
 && grep -v -E '^[[:space:]]*faster-whisper' \
        /opt/gateway/services/telegram_bot/requirements.txt  > /tmp/req-tb.txt \
 && pip install --no-cache-dir --upgrade pip wheel \
 && pip install --no-cache-dir -r /tmp/req-vg.txt -r /tmp/req-ng.txt -r /tmp/req-tb.txt \
 && apk del .build-deps \
 && (find /usr/lib/python3* -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true)

# s6-overlay service definitions + cont-init.
COPY rootfs/ /
RUN chmod +x \
        /etc/cont-init.d/*.sh \
        /etc/services.d/voice-gateway/run \
        /etc/services.d/notify-gateway/run \
        /etc/services.d/telegram-bot/run \
        /usr/lib/hass-ai-gateway/export-env.sh

# /init from the HA base image starts s6-overlay; do not override.
