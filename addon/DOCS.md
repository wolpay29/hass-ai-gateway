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

## User-editable config files

The add-on exposes editable files under `/addon_configs/<slug>/` (visible in
**Samba share** and the official **File editor** add-on). Defaults are seeded
on first start and your edits persist across add-on updates.

| File | What it does |
|------|--------------|
| `userconfig/entities.yaml` | Curated entity catalogue (primary parser + RAG keyword/meta overlay) |
| `userconfig/entities_blacklist.yaml` | Entity-id patterns excluded from RAG indexing |
| `userconfig/pre_llm_memory.md` | Free-text hints appended to the query-rewriter prompt (typo/STT fixes, pronoun rules) |
| `userconfig/post_llm_memory.md` | Free-text hints appended to all parser prompts (common errors, preferences, never-do rules) |
| `userconfig/whisper_vocabulary.md` | Vocabulary hints sent as Whisper `initial_prompt` (room names, smart-home jargon, names) |
| `menus.yaml` | Telegram bot menus, buttons, and action mappings |

### `entities.yaml`

Each entry exposes one HA entity to the gateway. The `keywords` list drives both
the legacy keyword parser and the RAG index; `meta` adds an extra hint to the LLM
prompt for tricky entities.

Status queries don't need a `get_state` action - the gateway pre-fetches the
live state of every entity in this list and shows it to the LLM, so any
question about the current value works automatically. Just list the actions
that change something.

```yaml
entities:
  - id: light.living_room
    description: "Living room light"
    keywords: ["living room", "lounge", "downstairs light"]
    actions: ["turn_on", "turn_off", "toggle"]
    domain: light
    meta: ""

  - id: switch.garden_pump
    description: "Garden irrigation pump"
    keywords: ["garden pump", "irrigation", "sprinkler"]
    actions: ["turn_on", "turn_off"]
    domain: switch
    meta: "Only switch on when weather is dry"

  - id: sensor.outdoor_temperature
    description: "Outdoor temperature"
    keywords: ["outside temperature", "how warm outside"]
    actions: []
    domain: sensor
    meta: ""

  - id: climate.living_room
    description: "Living room thermostat"
    keywords: ["living room heating", "thermostat"]
    actions: ["set_temperature", "set_hvac_mode"]
    domain: climate
    meta: ""
```

### `entities_blacklist.yaml`

Patterns matched here are dropped from the RAG index and can never be selected
by the LLM. Accepts exact `entity_id` strings or Unix-style globs (`*`, `?`).

```yaml
blacklist:
  - sensor.zigbee2mqtt_bridge_state   # exact match
  - sensor.*_battery_level            # glob — all battery sensors
  - automation.test_*                 # glob — all test automations
```

### `pre_llm_memory.md` / `post_llm_memory.md`

Free-text Markdown appended to the LLM prompt. Write hints **outside** the
HTML comment block — everything inside `<!-- ... -->` is ignored by the gateway.

**`pre_llm_memory.md`** is injected before the RAG search (query-rewriter stage).
Use it for STT typo fixes and pronoun rules.

```markdown
## Common STT errors
- "livving room", "livingroom" -> living room
- "pump" without context -> garden pump

## Ambiguous terms
- "upstairs" alone is ambiguous — leave as-is, ask for clarification
```

**`post_llm_memory.md`** is appended to every parser prompt (primary, RAG, fallback).
Use it for action preferences and never-do rules.

```markdown
## Preferences
- If user says "all off", use group entities where available

## Never do
- Never trigger automation.vacation_mode — always ask first
```

### `whisper_vocabulary.md`

Free-text Markdown sent to the Whisper STT model as `initial_prompt`. Whisper
prefers tokens that appear in the prompt, so this dramatically improves the
recognition of German smart-home terms, room names, and personal names. HTML
comments are stripped before use - leaving only the comment block disables
the feature (Whisper default behaviour).

```markdown
Wohnzimmer, Schlafzimmer, Kueche, Erdgeschoss, Obergeschoss.
Rolladen, Wallbox, Photovoltaik, Wechselrichter, Pool-Pumpe.
Paul, Max, Sophie.
```

Restart the add-on after editing.

After editing: restart the add-on. After editing `entities.yaml` while RAG is
enabled, also send `/rag_rebuild` in the Telegram chat (or `POST /rag_rebuild`
to the voice gateway, see "RAG rebuild from HA" below).

All other settings (tokens, URLs, model names, RAG/fallback toggles) are in the
**Configuration** tab below — no file editing required.

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
server. The repo's `infra/faster_whisper/docker-compose.yml`
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
  max_actions_per_command: 0                        # 0 = unlimited
```

`mcp_allowed_tools` is the whitelist used in `FALLBACK_MODE=2`. Empty = no
filter (all tools the HA MCP server exposes are allowed).

The values in this section are also reused as defaults by `llm_preprocessor`
and `rag` when those leave their `url` / `model` / `api_key` blank.

### `voice_gateway` / `notify_gateway`

```yaml
voice_gateway:
  port: 8765
  api_key: ""               # X-Api-Key header expected from clients; empty = no auth
  telegram_push: true
  reply_with_transcript: true
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
  enabled: true
  top_k: 15
  distance_threshold: 0.0   # 0 = aus; example ~0.5 for nomic-embed-text-v2
  keyword_boost: 0.3
  embed_url: ""        # blank = reuse lmstudio.url
  embed_model: "text-embedding-nomic-embed-text-v2-moe"
  embed_dim: 768
```

`distance_threshold` drops candidates whose embedding distance is above the
value (the best candidate is always kept as a safety net). `top_k` remains a
hard upper bound; the stricter of the two limits wins. With `0` (default)
only `top_k` applies - identical to previous behaviour. To tune: trigger a
`/rag_rebuild`, send a voice command, look at the `Top-5: [(eid, dist), ...]`
log line and pick a threshold slightly above the typical correct-hit
distance.

The SQLite vector index lives at `/data/rag/entities.sqlite`. Trigger a
rebuild from Telegram with `/rag_rebuild`, from a terminal with
`docker exec addon_<slug> python -m core.rag.index`, or via the voice
gateway endpoint:

```bash
curl -X POST http://<addon-ip>:8765/rag_rebuild \
     -H "X-Api-Key: $GATEWAY_API_KEY"
```

You can also wire that into HA via `rest_command`:

```yaml
rest_command:
  rag_rebuild:
    url: "http://localhost:8765/rag_rebuild"
    method: POST
    headers:
      X-Api-Key: "<your gateway api key>"
```

Then call `service: rest_command.rag_rebuild` from any HA automation,
script, or button card.

### `llm_preprocessor`

```yaml
llm_preprocessor:
  enabled: true
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

### `history`

```yaml
history:
  size: 0                       # 0 = no history; each request is independent
  include_assistant: true       # let the LLM see its own past replies
  append_executions: false      # add "executed: ..." lines so follow-ups have context
```

### Required fields

Nothing is required globally — every "required" field depends on which
services you enable. The HA UI cannot express conditional requirements, so
the affected field labels say "required if X is enabled", and the add-on
validates on startup and refuses to start when something essential is
missing:

| Field | Required when |
|-------|---------------|
| `telegram.bot_token` | `services.telegram_bot` is on |
| `telegram.chat_id` (≠ 0) | `services.telegram_bot` is on |
| `lmstudio.url` | `services.voice_gateway` or `services.telegram_bot` is on |

Pure example: if you only use `notify_gateway` (HA → TTS / Telegram fan-out
without LLM commands), all three are optional.

Strongly recommended (warning only — feature degrades gracefully):

| Field | Effect when missing |
|-------|---------------------|
| `whisper.external_url` | Voice input (audio uploads, Telegram voice messages) unavailable; text still works |
| `home_assistant.token` | Falls back to the supervisor token — only needed for external HA instances |

Auto-fallbacks (no warning):

- `rag.embed_url` empty → reuses `lmstudio.url`
- `llm_preprocessor.url` / `model` / `api_key` empty → reuses corresponding `lmstudio.*`

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
