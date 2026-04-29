# Hass AI Gateway — Documentation

This add-on runs three Python services in one container:

- **voice_gateway** — FastAPI server on port `8765` for RPi / ESP32 voice
  clients. Accepts audio uploads or plain text, runs the unified processing
  pipeline (`core/processor.py`), and optionally returns synthesised TTS audio.
- **notify_gateway** — FastAPI server on port `8766` that HA can post
  notification payloads to. Fans out the message to TTS endpoints and / or
  Telegram per request.
- **telegram_bot** — Long-polling Telegram bot. Handles voice + text commands
  and the menu system (`menus.yaml`).

All three share `core/` (HA REST client, LM Studio LLM, optional semantic
entity retrieval), which is why they live in one container instead of three.

---

## Configuration

Configuration is grouped in the UI. The sections below mirror what you'll see
in the **Configuration** tab.

### `services` — which to run

Toggle each service on or off. A disabled service stays present in the
container but sleeps (s6 does not run its `main.py`).

```yaml
services:
  voice_gateway: true
  notify_gateway: true
  telegram_bot: true
```

### `telegram`

```yaml
telegram:
  bot_token: "<from @BotFather>"
  chat_id: 123456789
```

`chat_id` is the numeric ID the bot is allowed to talk to (your account).
Required when `services.telegram_bot` or
`voice_gateway.telegram_push` is true.

### `home_assistant`

```yaml
home_assistant:
  url: "http://supervisor/core"   # default — uses the Supervisor proxy
  token: ""                       # blank = use the auto-injected SUPERVISOR_TOKEN
  service_timeout: 15
```

Leaving `token` blank makes the add-on use `SUPERVISOR_TOKEN`, which already
has the permissions the gateway needs. Override it with a long-lived
access token if you want to call HA from a different host.

### `whisper`

External Whisper only in v1.0:

```yaml
whisper:
  external_url: "http://10.1.10.78:10300/v1/audio/transcriptions"
  external_model: "deepdml/faster-whisper-large-v3-turbo-ct2"
  language: "de"
```

Point `external_url` at any OpenAI-compatible `/v1/audio/transcriptions`
server. The repo's `gateway/services/faster_whisper/docker-compose.yml`
ships a working setup.

### `lmstudio`

```yaml
lmstudio:
  url: "http://10.1.10.78:1234"
  model: "qwen2.5-7b-instruct"
  api_key: ""
  timeout: 30
  temperature: 0.1
  no_think: true
  context_length: 8000
  mcp_allowed_tools: "HassTurnOn,HassTurnOff,..."   # comma-separated
```

`mcp_allowed_tools` is the whitelist used in `FALLBACK_MODE=2`. Empty = no
filter (all tools the HA MCP server exposes are allowed).

### `voice_gateway` / `notify_gateway`

```yaml
voice_gateway:
  port: 8765
  api_key: ""        # X-Api-Key header expected from clients; empty = no auth
  telegram_push: true
notify_gateway:
  port: 8766
  http_timeout: 10
```

If you change `port`, also change the **Network** section in the add-on UI to
expose the new port to the host.

### `tts`

```yaml
tts:
  external_url: "http://10.1.10.78:10400/tts"
  external_voice: "de_DE-thorsten-low"
```

Leave `external_url` blank to skip TTS — voice_gateway returns JSON instead
of audio.

### `rag`

```yaml
rag:
  enabled: false
  top_k: 15
  keyword_boost: 0.3
  embed_url: ""        # blank = reuse lmstudio.url
  embed_model: "text-embedding-nomic-embed-text-v2-moe"
  embed_dim: 768
```

The SQLite vector index lives at `/data/rag/entities.sqlite`. Trigger a
rebuild from Telegram with `/rag_rebuild`.

### `llm_preprocessor`

```yaml
llm_preprocessor:
  enabled: false
  url: ""              # blank = reuse lmstudio.url
  api_key: ""          # blank = reuse lmstudio.api_key
  model: ""            # blank = reuse lmstudio.model
  timeout: 30
  temperature: 0.1
```

When enabled, an extra small LLM call classifies intent
(`command | smalltalk`), fixes typos / STT errors, and resolves pronouns from
history before the main pipeline runs.

### `fallback`

```yaml
fallback:
  mode: 0                          # 0=off, 1=REST, 2=MCP
  rest_max_entities: 0             # 0 = no limit
  rest_domains: "light,switch,sensor,binary_sensor,climate,automation,cover"
```

### `advanced`

```yaml
advanced:
  llm_history_size: 0
  history_include_assistant: true
  history_append_executions: false
  max_actions_per_command: 0
  voice_reply_with_transcript: true
  notify_http_timeout: 10
```

---

## Calling the gateways from HA

### `notify_gateway` — `notify` via `rest_command`

```yaml
# configuration.yaml
rest_command:
  notify_assistant:
    url: "http://localhost:8766/notify"
    method: POST
    content_type: "application/json"
    payload: >-
      {"message": "{{ message }}",
       "targets": [{"type": "telegram"},
                   {"type": "tts", "url": "http://192.168.1.50:8765"}]}
```

```yaml
# automation.yaml — example
- alias: "Doorbell announcement"
  trigger: ...
  action:
    - service: rest_command.notify_assistant
      data:
        message: "Es klingelt an der Tür"
```

### `voice_gateway` — text command

```yaml
rest_command:
  voice_gateway_text:
    url: "http://localhost:8765/text"
    method: POST
    content_type: "application/json"
    payload: '{"text": "{{ text }}", "device_id": "ha"}'
```

---

## Persistent storage

| Path                              | Purpose                                                     |
|-----------------------------------|-------------------------------------------------------------|
| `/data/voice/`                    | Downloaded voice files from Telegram (auto-created)         |
| `/data/rag/entities.sqlite`       | RAG vector index (auto-created on first `/rag_rebuild`)     |
| `/data/options.json`              | Supervisor-managed config snapshot (do not edit by hand)    |

Everything under `/data/` survives add-on restarts and updates.

---

## Troubleshooting

- **"telegram_bot enabled but telegram.bot_token is empty"** — fill in
  `telegram.bot_token` and restart the add-on.
- **`HA_TOKEN` errors / 401 from HA** — leave `home_assistant.token` blank to
  fall back to `SUPERVISOR_TOKEN`, or paste a long-lived access token.
- **`faster-whisper` import errors** — should never happen; v1.0 hard-pins
  `WHISPER_BACKEND=external`. If you see this, file an issue with logs.
- **Image build slow on Pi** — first build can take 10–15 min on armv7 / aarch64.
  Subsequent rebuilds reuse Docker layer cache.

## Local development

```bash
cd addon
./build-local.sh amd64           # or aarch64 / armv7

mkdir -p _data
cp options.example.json _data/options.json   # edit values
docker run --rm \
    -p 8765:8765 -p 8766:8766 \
    -v $PWD/_data:/data \
    local/hass-ai-gateway-amd64:dev
```

---

## Regenerating the icon / logo

The PNGs are generated with Pillow:

```python
from PIL import Image, ImageDraw, ImageFont

for size, name in [(256, "icon.png"), ((250, 100), "logo.png")]:
    img = Image.new("RGB", size if isinstance(size, tuple) else (size, size), "#0F172A")
    draw = ImageDraw.Draw(img)
    text = "SA"
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf",
                                   size if isinstance(size, int) else 60)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    canvas = img.size
    draw.text(((canvas[0] - w) / 2 - bbox[0], (canvas[1] - h) / 2 - bbox[1]),
              text, fill="#FFFFFF", font=font)
    img.save(name)
```
