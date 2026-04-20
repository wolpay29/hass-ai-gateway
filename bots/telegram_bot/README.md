# Telegram Home Assistant Bot

Telegram bot for Home Assistant control with menu-based actions, battery monitoring, and optional voice-message transcription via Faster Whisper.

## What it does

- Shows a persistent Telegram main menu with submenus for gate and pool control.
- Reads the current battery SOC and PV surplus from Home Assistant.
- Sends a notification when the battery level is above a configured threshold.
- Lets you quickly turn on the pool heating with a button via Home Assistant automations.
- Downloads Telegram voice messages and transcribes them (local Faster Whisper or external API).
- Accepts free-form voice/text commands and routes them to Home Assistant via an LLM (LM Studio).
- Three-tier fallback: curated entity whitelist → live REST list → MCP server with tool use.

## Key files

- `telegram_ha_bot.py`  
  Main bot code.

- `bot/voice.py`  
  Voice download directory handling and Faster Whisper transcription.

- `bot/config.py`  
  Loads environment variables and application settings.

- `.env`  
  Config values (bot token, chat ID, HA URL, HA token, thresholds, Whisper settings). Not committed.

- `requirements.txt`  
  Python dependencies (`python-telegram-bot[job-queue]`, `requests`, `python-dotenv`, `faster-whisper`).

- `systemd/telegram-bot.service`  
  Example systemd service file; can be copied to `/etc/systemd/system/`.

## Requirements

- Python 3
- Telegram bot token
- Home Assistant instance with automations for the bot
- Home Assistant long-lived access token
- FFmpeg installed on the system
- Sufficient CPU performance for local Whisper transcription

## Setup

### 1. Config

Create a `.env` file in the same folder as `telegram_ha_bot.py`:

```ini
BOT_TOKEN=your_telegram_bot_token
MY_CHAT_ID=-123456789

HA_URL=http://10.1.10.100:8123
HA_TOKEN=your_long-lived_token

CHECK_INTERVAL_SECONDS=300
BATTERY_THRESHOLD=80

VOICE_REPLY_WITH_TRANSCRIPT=true
VOICE_DOWNLOAD_DIR=data/voice

WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

# LM Studio (OpenAI-kompatibel + /api/v1/chat fuer MCP)
LMSTUDIO_URL=http://10.1.10.78:1234
LMSTUDIO_MODEL=qwen/qwen3.5-9b
LMSTUDIO_API_KEY=sk-lm-...
LMSTUDIO_TIMEOUT=30
LMSTUDIO_TEMPERATURE=0.1

# Fallback: 0=off, 1=REST (live HA entities), 2=MCP (LM Studio with HA MCP server)
FALLBACK_MODE=2
FALLBACK_REST_DOMAINS=
FALLBACK_REST_MAX_ENTITIES=0

# Mode 2 (MCP) settings
LMSTUDIO_CONTEXT_LENGTH=8000
LMSTUDIO_MCP_ALLOWED_TOOLS=HassTurnOn,HassTurnOff,HassCancelAllTimers,HassBroadcast,HassClimateSetTemperature,HassLightSet,GetDateTime,GetLiveContext
```

### Fallback modes

The bot first tries the curated `bot/entities.yaml` whitelist. If nothing matches (or a matched entity needs parameters like `set_temperature`), it falls through to the configured fallback:

| `FALLBACK_MODE` | Behaviour |
| --- | --- |
| `0` | Off — unmatched commands return an error. |
| `1` | REST fallback. Pulls all HA entities via `/api/states`, feeds them live to the LLM, then executes a standard `turn_on/off/toggle/get_state`. Domain filter via `FALLBACK_REST_DOMAINS` (empty / `{}` / `[]` = all). Cap via `FALLBACK_REST_MAX_ENTITIES` (0 = no limit). |
| `2` | MCP fallback. Sends the transcript to LM Studio's native `/api/v1/chat` with the HA MCP server attached as `ephemeral_mcp` integration. LM Studio picks the tools, calls HA, and returns a natural-language answer. Only mode that can set parameters (temperature, brightness, cover position, …). |

### LM Studio setup for Mode 2

In **Developer → Server Settings**:

- Server running on `0.0.0.0:1234`
- **Allow per-request MCPs** enabled
- **API Auth** enabled; paste the key into `LMSTUDIO_API_KEY`
- Load a tool-capable model (Qwen ≥7B works well)

No `mcp.json` is needed — the bot sends the HA MCP server as an ephemeral integration with every request.

The `LMSTUDIO_MCP_ALLOWED_TOOLS` whitelist is forwarded to LM Studio so only those HA tools are exposed to the model. Set it to empty / `{}` / `[]` to allow all tools the HA MCP server reports.

### 2. Virtual environment

Inside the bot folder:

```bash
cd /root/smarthome/bots/telegram_bot
python3 -m venv telegram_bot_env
source telegram_bot_env/bin/activate
pip install -r requirements.txt
deactivate
```

### 3. Install FFmpeg

Faster Whisper uses FFmpeg for audio handling. Install it on the host system:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 4. Test manually

```bash
cd /root/smarthome/bots/telegram_bot
source telegram_bot_env/bin/activate
python telegram_ha_bot.py
```

Use `Ctrl+C` to stop the bot while testing.

### 5. Run with systemd

Copy the service file:

```bash
cp /root/smarthome/bots/telegram_bot/systemd/telegram-bot.service /etc/systemd/system/telegram-bot.service
```

Reload systemd, enable and start the bot:

```bash
systemctl daemon-reload
systemctl enable telegram-bot.service
systemctl restart telegram-bot.service
systemctl status telegram-bot.service
```

Check logs:

```bash
journalctl -u telegram-bot.service -n 50 --no-pager
```

## Voice transcription notes

- Voice messages are downloaded from Telegram and transcribed locally.
- `WHISPER_MODEL=small` uses a small Whisper model for CPU-friendly performance.
- `WHISPER_COMPUTE_TYPE=int8` enables quantization for faster inference.
- `VOICE_REPLY_WITH_TRANSCRIPT=true` enables reply with transcript text.
- Whisper handles language detection automatically when no language is forced.
- Fuller settings like `language` and `beam_size` can be added via `.env` if needed. [web:464][web:468]

## Recommended config (CPU)

For light CPU usage and decent quality:

```ini
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
VOICE_REPLY_WITH_TRANSCRIPT=true
```

## Manual connection tests

Useful curl recipes to verify each integration independently.

### 1. Home Assistant MCP server (POST only)

```bash
curl -X POST http://<HA_URL>/api/mcp \
  -H "Authorization: Bearer <HA_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

`GET` returns `Only POST method is supported` — that is expected.

### 2. LM Studio health (OpenAI-compatible)

```bash
curl http://<LMSTUDIO_URL>/v1/models \
  -H "Authorization: Bearer <LMSTUDIO_API_KEY>"
```

### 3. End-to-end MCP call (the exact shape the bot sends)

```bash
curl http://<LMSTUDIO_URL>/api/v1/chat \
  -H "Authorization: Bearer <LMSTUDIO_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.5-9b",
    "input": "Give me details about my pool heater",
    "integrations": [
      {
        "type": "ephemeral_mcp",
        "server_label": "home-assistant",
        "server_url": "http://<HA_URL>/api/mcp",
        "allowed_tools": ["HassTurnOn","HassTurnOff","HassClimateSetTemperature","HassLightSet","GetLiveContext"],
        "headers": { "Authorization": "Bearer <HA_TOKEN>" }
      }
    ],
    "context_length": 8000
  }'
```

A working response contains `output[]` items with `type: "tool_call"` (HA tools that were invoked) and `type: "message"` (the natural-language answer). `stats.input_tokens > 1000` is a good signal that the tool list was actually fetched; if it stays around 80, LM Studio didn't pull the MCP tools (usually `Allow per-request MCPs` is off or auth is missing).

### 4. Home Assistant REST (used by Mode 1)

```bash
curl http://<HA_URL>/api/states \
  -H "Authorization: Bearer <HA_TOKEN>" | head
```

## Log markers

Every request is tagged so you can trace which path served it:

- `[Dispatch]` — routing decisions, FALLBACK_MODE, needs_fallback handoff.
- `[LLM]` — primary path (entities.yaml).
- `[Fallback Mode 1 / REST]` — live-entity fallback.
- `[Fallback Mode 2 / MCP]` — LM Studio + HA MCP; logs `tool_calls=[...]` and token counts.
- `[LLM Step2]` — natural-language reply generation for `get_state` queries.

## Changelog

### v0.3.0 (2026-04-20)

- Added three-tier fallback system (off / REST / MCP) for free-form commands
- Renamed `OLLAMA_*` config to `LMSTUDIO_*` (the bot has always talked to LM Studio)
- Added `needs_fallback` signal so parameterised commands on known entities reach MCP
- Added `LMSTUDIO_MCP_ALLOWED_TOOLS` + `LMSTUDIO_CONTEXT_LENGTH` .env knobs
- Structured log prefixes for every dispatch path

### v0.2.0 (2026-04-17)

- Added voice message transcription with Faster Whisper
- Added Whisper runtime config via .env
- Added optional transcript replies and voice download dir