# Architecture

This project is organised so that all command logic — transcribe audio, call
the LLM, decide which Home Assistant actions to fire, apply fallbacks, track
conversation history — lives in **one place** and every frontend (Telegram,
voice gateway, future web UI, etc.) is a thin adapter over it.

## Folder layout

```
smarthome/
├── core/                         ← framework-agnostic command logic
│   ├── processor.py              ── single source of truth (transcript → actions)
│   ├── config.py                 ── .env loader + all settings
│   ├── llm.py                    ── LM Studio client: parse_command / parse_command_rag / ...
│   ├── llm_lmstudio.py           ── MCP fallback (Mode 2)
│   ├── ha.py                     ── Home Assistant REST client
│   ├── voice.py                  ── Whisper transcription (local or external)
│   ├── entities.yaml             ── curated entity catalogue
│   └── rag/                      ── RAG index, embeddings, sqlite-vec store
│
├── bots/
│   ├── telegram_bot/             ← Telegram adapter
│   │   ├── telegram_ha_bot.py    ── entry point (python-telegram-bot)
│   │   └── bot/
│   │       ├── handlers.py       ── voice/text handler → core.processor → Telegram Markdown
│   │       ├── callbacks.py      ── inline-button callbacks (Tor, Pool, …)
│   │       ├── menu.py           ── reply-keyboard menu
│   │       └── battery.py        ── periodic battery notification job
│   │
│   └── voice_gateway/            ← HTTP adapter
│       ├── main.py               ── FastAPI: /audio, /text, /health
│       └── requirements.txt
│
├── devices/
│   └── raspberry_pi/             ← on-device client
│       ├── voice_client.py       ── openWakeWord → record → POST → TTS
│       └── requirements.txt
│
└── esp/                          ← ESP8266/ESP32 firmware projects (unchanged)
```

## Dependency rules

```
      ┌─────────────────────────────────────────────┐
      │                   core/                     │  ← knows about nothing else
      │  processor → llm / ha / voice / config      │
      └────────────▲─────────────────▲──────────────┘
                   │                 │
      ┌────────────┴──────┐  ┌───────┴──────────┐
      │ bots/telegram_bot │  │ bots/voice_gateway│ ← adapters, depend only on core/
      └───────────────────┘  └──────────────────┘
                                      ▲
                                      │ HTTP
                                      │
                       ┌──────────────┴─────────────┐
                       │  devices/raspberry_pi      │ ← dumb edge device
                       └────────────────────────────┘
```

- `core/` **never** imports from `bots/` or `devices/`.
- `bots/telegram_bot/` imports from `core/` but not from `bots/voice_gateway/`.
- `bots/voice_gateway/` imports from `core/` but not from `bots/telegram_bot/`.
- Devices talk to the gateway only over HTTP — no shared code.

That means you can change core behaviour once and both bots pick it up, and you
can delete any one adapter without touching the others.

## Request lifecycle

### Telegram voice message
1. `bots/telegram_bot/bot/handlers.py::handle_voice` downloads the `.ogg`.
2. Transcribes via `core.voice.transcribe_audio`.
3. Calls `core.processor.process_transcript(transcript, chat_id=<telegram_id>)`.
4. `_format_reply()` turns the result dict into Markdown; sent via `reply_text`.

### Raspberry Pi voice command
1. `devices/raspberry_pi/voice_client.py` detects "Hey Jarvis" with openWakeWord.
2. Records until silence (simple RMS-based VAD).
3. POSTs WAV to `bots/voice_gateway/main.py::/audio`.
4. Gateway calls `core.voice.transcribe_audio` then `core.processor.process_transcript`.
5. Returns the result JSON (`reply` already contains the answer — state queries, conditions and calculations are resolved inside the single RAG parser call).
6. RPi speaks `result["reply"]` with `pyttsx3`.
7. Gateway optionally also pushes the receipt to Telegram (`GATEWAY_TELEGRAM_PUSH=true`).

Both paths hit the **same** `process_transcript()` — identical RAG lookup,
identical fallback behaviour, identical history handling.

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

There is **one** `.env` file: `bots/telegram_bot/.env`. `core/config.py`
finds it automatically. The gateway and Telegram bot share every setting
(Whisper backend, LM Studio URL, RAG settings, fallback mode, …).

Gateway-only knobs (added to the same `.env`):

| Var | Default | Purpose |
|---|---|---|
| `GATEWAY_API_KEY` | *(empty)* | Require `X-Api-Key` header on requests. Empty = no auth (LAN only). |
| `GATEWAY_PORT`    | `8765`    | Port to listen on. |
| `GATEWAY_TELEGRAM_PUSH` | `true` | Send a Markdown receipt of each gateway command to `MY_CHAT_ID`. |
| `DOTENV_PATH`     | *(auto)*  | Override the `.env` location if you move it. |

## Running

### Telegram bot
```bash
cd bots/telegram_bot
python telegram_ha_bot.py
```

### Voice gateway
```bash
cd bots/voice_gateway
pip install -r requirements.txt
python main.py   # listens on 0.0.0.0:8765
```

### Raspberry Pi client
```bash
# On the Pi
cd devices/raspberry_pi
sudo apt install -y portaudio19-dev espeak espeak-data libespeak-dev
pip install -r requirements.txt
export GATEWAY_URL="http://<ai-pc-ip>:8765"
export GATEWAY_API_KEY="<your-key>"          # must match gateway .env
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
strategy, new error type): edit `core/processor.py`. Both Telegram and the
gateway pick up the change at next restart.
