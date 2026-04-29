# Architecture

This project is organised so that all command logic — transcribe audio, call
the LLM, decide which Home Assistant actions to fire, apply fallbacks, track
conversation history — lives in **one place** and every frontend (Telegram,
voice gateway, notify gateway, future web UI, etc.) is a thin adapter over it.

## Folder layout

```
gateway/
├── core/                          <- framework-agnostic command logic
│   ├── processor.py               ── single source of truth (transcript -> actions)
│   ├── config.py                  ── .env loader + all settings
│   ├── llm.py                     ── LM Studio client: parse_command / parse_command_rag / …
│   ├── llm_lmstudio.py            ── MCP fallback (Mode 2)
│   ├── ha.py                      ── Home Assistant REST client
│   ├── voice.py                   ── Whisper transcription (local or external)
│   ├── entities.yaml              ── curated entity catalogue
│   ├── entities_blacklist.yaml    ── entities excluded from RAG / LLM context
│   ├── prompts.yaml               ── all system prompts
│   └── rag/                       ── embeddings, sqlite-vec store, index, rewriter
│
├── services/
│   ├── telegram_bot/              <- Telegram adapter
│   │   ├── main.py                ── entry point; loads handlers from menus.yaml
│   │   ├── menus.yaml             ── ALL button/menu config (no code change to add menus)
│   │   └── bot/
│   │       ├── handlers.py        ── voice/text handler -> core.processor -> Telegram Markdown
│   │       ├── callbacks.py       ── inline-button callbacks + generic action dispatcher
│   │       ├── menu.py            ── reply-keyboard menu helpers
│   │       └── menu_config.py     ── menus.yaml loader
│   │
│   ├── voice_gateway/             <- HTTP adapter for RPi / ESP32 audio clients
│   │   ├── main.py                ── FastAPI: /audio, /text, /health
│   │   └── requirements.txt
│   │
│   ├── notify_gateway/            <- Webhook target for HA notifications
│   │   ├── main.py                ── FastAPI; fans out to TTS + Telegram
│   │   └── requirements.txt
│   │
│   ├── faster_whisper/            <- Optional standalone Whisper STT server
│   └── tts_server/                <- Optional standalone TTS server
│
├── devices/
│   └── raspberry_pi/              <- on-device voice client
│       ├── voice_client.py        ── openWakeWord -> record -> POST -> TTS playback
│       └── requirements.txt
│
└── systemd/                       <- systemd unit files + install.sh for bare-metal hosts
```

The same code is also packaged as a Home Assistant Supervisor add-on — see
[`addon/`](../addon) at the repo root. The add-on bundles `core/` + the three
gateway services into one container; `devices/` and the standalone STT/TTS
servers are out of scope for the add-on (they run elsewhere).

## Dependency rules

```
      ┌─────────────────────────────────────────────────┐
      │                    core/                        │  <- knows about nothing else
      │  processor -> llm / ha / voice / config / rag    │
      └────────────^──────────────^──────────────^──────┘
                   │              │              │
      ┌────────────┴────┐ ┌───────┴────────┐ ┌───┴──────────────┐
      │  telegram_bot   │ │  voice_gateway │ │  notify_gateway  │  <- adapters; only depend on core/
      └─────────────────┘ └────────────────┘ └──────────────────┘
                                  ^
                                  │ HTTP
                                  │
                     ┌────────────┴────────────┐
                     │  devices/raspberry_pi   │  <- dumb edge device
                     └─────────────────────────┘
```

- `core/` **never** imports from `services/` or `devices/`.
- Each `services/*` adapter imports from `core/` but not from sibling adapters.
- Devices talk to the gateway only over HTTP — no shared code.

That means you can change core behaviour once and every frontend picks it up,
and you can delete any single adapter without touching the others.

## Request lifecycle

### Telegram voice message
1. `services/telegram_bot/bot/handlers.py::handle_voice` downloads the `.ogg`.
2. Transcribes via `core.voice.transcribe_audio`.
3. Calls `core.processor.process_transcript(transcript, chat_id=<telegram_id>)`.
4. `_format_reply()` turns the result dict into Markdown; sent via `reply_text`.

### Raspberry Pi voice command
1. `devices/raspberry_pi/voice_client.py` detects the wake word with openWakeWord.
2. Records until silence (simple RMS-based VAD).
3. POSTs WAV to `services/voice_gateway/main.py::/audio`.
4. Gateway calls `core.voice.transcribe_audio`, then `core.processor.process_transcript`.
5. Returns the result JSON (`reply` already contains the answer — state queries,
   conditions and calculations are resolved inside the single RAG parser call).
6. RPi speaks `result["reply"]` with `pyttsx3`.
7. Gateway optionally also pushes the receipt to Telegram (`GATEWAY_TELEGRAM_PUSH=true`).

### HA notification
1. Home Assistant fires a `rest_command` / `notify` webhook to
   `services/notify_gateway/main.py`.
2. The gateway fans out to TTS (speaker / phone) and/or Telegram.
3. No LLM call — this path is just message routing.

All voice/text paths hit the **same** `process_transcript()` — identical RAG
lookup, identical fallback behaviour, identical history handling.

## History and `chat_id`

`core.llm._history` is a dict keyed by `chat_id: int`. Two callers that pass
the same `chat_id` share a conversation.

| Caller | `chat_id` used |
|---|---|
| Telegram | `update.effective_chat.id` (your real Telegram chat ID) |
| Voice gateway, numeric `device_id` | parsed directly as `int(device_id)` |
| Voice gateway, string `device_id`  | `abs(hash(device_id)) % 10**9` (stable, isolated) |

**To share history between Telegram and the RPi**, set the RPi's
`DEVICE_ID` env var to your Telegram chat ID (e.g. `DEVICE_ID=123456789`).
The LLM will then see one continuous conversation across both channels.

Leave `DEVICE_ID` as a name like `rpi-kitchen` and the RPi gets its own
isolated history space.

## Configuration

There is **one** canonical `.env`: [`gateway/.env`](../gateway/.env.example).
`core/config.py` finds it automatically (it walks up from the importing
service). All services share every setting — Whisper backend, LM Studio URL,
RAG settings, Telegram credentials, fallback mode, …

When the project runs as the HA add-on, options from the add-on Configuration
tab are exported into the same environment variables by
[`addon/rootfs/usr/lib/hass-ai-gateway/export-env.sh`](../addon/rootfs/usr/lib/hass-ai-gateway/export-env.sh)
— no `.env` file is needed inside the container.

Gateway-only knobs (added to the same `.env`):

| Var | Default | Purpose |
|---|---|---|
| `GATEWAY_API_KEY` | *(empty)* | Require `X-Api-Key` header on requests. Empty = no auth (LAN only). |
| `GATEWAY_PORT`    | `8765`    | Port to listen on. |
| `GATEWAY_TELEGRAM_PUSH` | `true` | Send a Markdown receipt of each gateway command to `MY_CHAT_ID`. |
| `DOTENV_PATH`     | *(auto)*  | Override the `.env` location if you move it. |

## Running

### Bare-metal / systemd (host install)

Use the unit files and installer in [`gateway/systemd/`](../gateway/systemd):

```bash
sudo gateway/systemd/install.sh
```

That creates a venv per service under `gateway/services/<svc>/<svc>_env/`,
copies the `.service` units to `/etc/systemd/system/`, and enables them.
The units assume the repo lives at `/root/hass-ai-gateway/`.

### HA Supervisor add-on

See [`addon/README.md`](../addon/README.md). Add the repo URL to the HA
Add-on Store, install **Hass AI Gateway**, fill in options, hit Start. The
container bundles `core/` + `services/{voice,notify}_gateway` + `telegram_bot`.

### Manual (one service at a time, for development)

```bash
# Telegram bot
cd gateway/services/telegram_bot
python main.py

# Voice gateway
cd gateway/services/voice_gateway
pip install -r requirements.txt
python main.py   # listens on 0.0.0.0:8765
```

### Raspberry Pi client

```bash
# On the Pi
cd gateway/devices/raspberry_pi
sudo apt install -y portaudio19-dev espeak espeak-data libespeak-dev
pip install -r requirements.txt
export GATEWAY_URL="http://<ai-pc-ip>:8765"
export GATEWAY_API_KEY="<your-key>"          # must match gateway/.env
export DEVICE_ID="rpi-wohnzimmer"            # or your Telegram chat_id
export WAKE_WORD="hey_jarvis"
python voice_client.py
```

## Extending

**To add a new frontend** (web page, ESP32-S3, HomeKit bridge, etc.):
1. Import `core.processor.process_transcript`.
2. Decide what `chat_id` to use.
3. Format the returned dict however your frontend wants.

You should not need to touch `core/` at all for most new frontends.

**To change command behaviour** (e.g. new fallback mode, different RAG
strategy, new error type): edit `core/processor.py`. Every adapter picks up
the change at next restart.
