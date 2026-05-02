# Hass AI Gateway Add-on

Voice + Telegram + Notify gateways for Home Assistant, packaged as a single
Supervisor add-on. Bundles three services from
[`../services/`](../services) on top of the shared [`../core/`](../core)
brain, each service individually toggleable from the add-on UI.

## How it works

You talk to your smart home via **Telegram** (text or voice message on your phone)
or via a **Raspberry Pi / ESP32** with a wake word ("Hey Jarvis") next to any room.

Each request flows through the same pipeline:

1. **Speech-to-text** — voice recordings are transcribed by an external Whisper
   server into plain text.
2. **Intent & query rewrite (pre-LLM)** — a small LLM call classifies the
   request as a command, smalltalk, or clarification, and normalizes the phrase
   for better search results.
3. **RAG entity retrieval** — the normalized query is turned into a vector
   embedding and matched against your HA entity catalogue (sqlite-vec KNN).
   Only the most relevant devices are forwarded to the main LLM, keeping the
   prompt small and accurate.
4. **LLM parser** — the local LLM (LM Studio) sees the transcript, the
   matching entities, and their current live states. It decides what action to
   take, evaluates conditions ("only turn off if > 15 W"), calculates parameters
   ("5 degrees above outdoor temp"), or asks a clarification question if the
   command is ambiguous.
5. **Home Assistant action** — the add-on calls the HA REST API to execute the
   action (turn on/off, set temperature, trigger automation, …).
6. **Reply** — Telegram gets a text reply with a status line per action.
   The RPi/ESP32 gets a WAV file spoken aloud via TTS.

**Telegram menus** (inline buttons) bypass the LLM entirely and trigger HA
automations directly, so frequently used actions stay instant and reliable.

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
   `https://github.com/wolpay29/hass-ai-gateway`, click **Add**.
2. Find **Hass AI Gateway** in the store and **Install**.
3. Open the **Configuration** tab, fill in at minimum:
   - `telegram_bot_token`, `telegram_chat_id`
   - `ha_token` (or leave blank to use the Supervisor token)
   - `lmstudio_url`
4. Save, then **Start** the add-on.

See `DOCS.md` (Documentation tab in HA) for the full option reference,
example HA `rest_command` / `notify` integrations, and troubleshooting.

## Whisper (STT)

Voice input requires an external OpenAI-compatible STT server.
The repo's [`../infra/faster_whisper/`](../infra/faster_whisper) ships a
docker-compose that starts one. Set `whisper_url` to its transcription
endpoint (e.g. `http://192.168.1.x:10300/v1/audio/transcriptions`).
Leave `whisper_url` empty if you only use text commands.

## Source

Built from [`../core/`](../core) and
[`../services/{voice_gateway,notify_gateway,telegram_bot}`](../services).
No code changes are required in those folders -- the add-on injects all
configuration via environment variables.
