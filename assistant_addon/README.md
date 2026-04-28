# Smarthome Assistant Add-on

Voice + Telegram + Notify gateways for Home Assistant, packaged as a single
Supervisor add-on. Bundles three services from the
[`assistant/`](../assistant) project into one container, each individually
toggleable from the add-on UI.

## What's inside

| Service        | Port  | Purpose                                                                     |
|----------------|-------|-----------------------------------------------------------------------------|
| voice_gateway  | 8765  | HTTP API for RPi / ESP32 voice clients (audio + text → HA service calls)    |
| notify_gateway | 8766  | Webhook target for HA notifications, fans out to TTS + Telegram             |
| telegram_bot   | —     | Telegram long-polling bot for chat-based control                             |

All three share `core/` (HA REST client, LM Studio LLM, optional RAG entity
retrieval), so a single container is the natural unit.

## Quick start

1. Add this repository to Home Assistant:
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, paste
   `https://github.com/wolpay29/smarthome`, click **Add**.
2. Find **Smarthome Assistant** in the store and **Install**.
3. Open the **Configuration** tab, fill in at minimum:
   - `telegram.bot_token`, `telegram.chat_id`
   - `home_assistant.token` (or leave blank to use the Supervisor token)
   - `lmstudio.url`
4. Save, then **Start** the add-on.

See `DOCS.md` (Documentation tab in HA) for the full option reference,
example HA `rest_command` / `notify` integrations, and troubleshooting.

## Whisper

External Whisper only in v1.0 (`WHISPER_BACKEND` is hard-pinned to `external`).
Run a separate Whisper server — `assistant/services/faster_whisper/` ships a
docker-compose that does this — and point `whisper.external_url` at it.
A dedicated `assistant_addon_whisper` add-on may ship later.

## Source

Built from [`assistant/core`](../assistant/core) and
[`assistant/services/{voice_gateway,notify_gateway,telegram_bot}`](../assistant/services).
No code changes are required in those folders — the add-on injects all
configuration via environment variables.
