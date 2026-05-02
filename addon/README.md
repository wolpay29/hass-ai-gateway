# Hass AI Gateway Add-on

Voice + Telegram + Notify gateways for Home Assistant in a single add-on.

## Pipeline

1. **STT** — voice is transcribed by an external Whisper server.
2. **Preprocessor** — small LLM call classifies intent and fixes typos.
3. **RAG** — query is embedded and matched against your HA entity catalogue.
4. **LLM parser** — LM Studio sees the transcript, matched entities, and live states; decides what to do.
5. **HA action** — REST call to execute the result.
6. **Reply** — Telegram gets text; RPi/ESP32 gets WAV via TTS.

Telegram inline buttons bypass the LLM and call HA directly.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| voice_gateway | 8765 | HTTP API for RPi / ESP32 audio + text |
| notify_gateway | 8766 | HA webhook → TTS + Telegram fan-out |
| telegram_bot | — | Long-polling bot for chat control |

## Quick start

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, paste `https://github.com/wolpay29/hass-ai-gateway`.
2. Install **Hass AI Gateway**.
3. Open **Configuration**, fill in at minimum:
   - `telegram` → `bot_token`, `chat_id`
   - `lmstudio` → `url`
4. **Start** the add-on.

See the **Documentation** tab for the full option reference.

## Whisper (STT)

Point `whisper.url` at any OpenAI-compatible `/v1/audio/transcriptions` server.
`infra/faster_whisper/` ships a ready-to-use docker-compose. Leave empty for text-only use.
