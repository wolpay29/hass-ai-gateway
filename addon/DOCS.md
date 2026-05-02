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

After editing: restart the add-on. After editing `entities.yaml` while RAG is
enabled, also send `/rag_rebuild` in the Telegram chat (or `POST /rag_rebuild`
to the voice gateway, see "RAG rebuild from HA" below).

All other settings (tokens, URLs, model names, RAG/fallback toggles) are in the
**Configuration** tab below — no file editing required.

---

## Configuration

All settings are flat fields in the **Configuration** tab — no nested sections.
The groups below are for documentation purposes only.

### Services — which to run

Toggle each service on or off. A disabled service stays present in the
container but sleeps (s6 does not run its `main.py`).

| Key | Default |
|-----|---------|
| `enable_voice_gateway` | `true` |
| `enable_notify_gateway` | `true` |
| `enable_telegram_bot` | `true` |

### Telegram

| Key | Notes |
|-----|-------|
| `telegram_bot_token` | From @BotFather. Required when `enable_telegram_bot` is on. |
| `telegram_chat_id` | Your numeric Telegram user ID — the bot only answers to this ID. |

### Home Assistant

| Key | Default | Notes |
|-----|---------|-------|
| `ha_url` | `http://supervisor/core` | Default works inside the add-on. |
| `ha_token` | _(empty)_ | Blank = use the auto-injected SUPERVISOR_TOKEN. |
| `ha_service_timeout` | `15` | Seconds. |
| `ha_dry_run` | `false` | When on, service calls are only logged — no real HA actions are executed. |

`ha_dry_run` is useful while tuning prompts (so a misfire doesn't unlock the front door). It only blocks `call_service` — `get_state` and bulk state reads stay live.

### Whisper (STT)

| Key | Default | Notes |
|-----|---------|-------|
| `whisper_url` | _(empty)_ | OpenAI-compatible `/v1/audio/transcriptions` endpoint. Required for voice input. |
| `whisper_model` | `deepdml/faster-whisper-large-v3-turbo-ct2` | Model name sent to the server. |

Point `whisper_url` at any compatible STT server. The repo's `infra/faster_whisper/docker-compose.yml` ships a ready-to-use setup.

### LM Studio

| Key | Default | Notes |
|-----|---------|-------|
| `lmstudio_url` | _(empty)_ | Required when voice gateway or Telegram bot is enabled. |
| `lmstudio_model` | `qwen2.5-7b-instruct` | Must be loaded in LM Studio. |
| `lmstudio_api_key` | _(empty)_ | Leave empty if the server has no auth. |
| `lmstudio_timeout` | `30` | Seconds. |
| `lmstudio_temperature` | `0.1` | 0.0–0.3 recommended. |
| `lmstudio_no_think` | `true` | Suppresses `<think>` blocks on reasoning models. |
| `lmstudio_context_length` | `8000` | Context window for MCP fallback (mode 2). |
| `lmstudio_mcp_allowed_tools` | _(see example)_ | Comma-separated whitelist for fallback mode 2. Empty = allow all. |
| `lmstudio_max_actions_per_command` | `0` | 0 = unlimited. |

These values are also reused as defaults by the preprocessor and RAG when those leave their own URL / model / API key blank.

### Voice Gateway / Notify Gateway

| Key | Default | Notes |
|-----|---------|-------|
| `voice_port` | `8765` | Change the Network section too if you override this. |
| `voice_api_key` | _(empty)_ | X-Api-Key header expected from clients; empty = no auth. |
| `voice_telegram_push` | `true` | Forward voice replies to Telegram (requires Telegram bot enabled). |
| `voice_reply_with_transcript` | `true` | Include the transcript in the Telegram receipt. |
| `notify_port` | `8766` | |
| `notify_http_timeout` | `10` | Seconds. |

### TTS

| Key | Default | Notes |
|-----|---------|-------|
| `tts_url` | _(empty)_ | External TTS server. Leave empty — voice gateway returns JSON instead of audio. |
| `tts_voice` | `de_DE-thorsten-low` | Voice ID sent to the TTS server. |

### RAG

| Key | Default | Notes |
|-----|---------|-------|
| `rag_enabled` | `true` | Use vector retrieval instead of `entities.yaml` keyword lookup. |
| `rag_top_k` | `15` | Max candidates per query. |
| `rag_distance_threshold` | `0.0` | 0 = off. Drops candidates above this distance (best candidate always kept). |
| `rag_keyword_boost` | `0.3` | 0 = pure vector; higher = stronger keyword preference. |
| `rag_embed_url` | _(empty)_ | Leave empty to reuse `lmstudio_url`. |
| `rag_embed_model` | `text-embedding-nomic-embed-text-v2-moe` | |
| `rag_embed_dim` | `768` | Must match the embedding model. Index rebuilds automatically when changed. |

`rag_distance_threshold` drops candidates whose embedding distance is above the
value (the best candidate is always kept as a safety net). `rag_top_k` remains a
hard upper bound; the stricter of the two limits wins. With `0` (default)
only `rag_top_k` applies. To tune: trigger a `/rag_rebuild`, send a voice
command, look at the `Top-5: [(eid, dist), ...]` log line and pick a threshold
slightly above the typical correct-hit distance.

The SQLite vector index lives at `/data/rag/entities.sqlite`. Trigger a
rebuild from Telegram with `/rag_rebuild`, from a terminal with
`docker exec addon_<slug> python -m core.rag.index`, or from Home
Assistant (see below).

#### RAG rebuild button + status sensors in HA

Add the following blocks to your `configuration.yaml`. Replace
`<your gateway api key>` with the value you set in
`voice_api_key` (or remove the `headers:` block if you left it
empty).

```yaml
# --- 1. Status sensor (polls every 60 s, no rebuild triggered) -----------
rest:
  - resource: "http://localhost:8765/rag_status"
    scan_interval: 60
    headers:
      X-Api-Key: "<your gateway api key>"
    sensor:
      - name: "RAG Index Entities"
        unique_id: rag_index_entities
        value_template: "{{ value_json.count }}"
        unit_of_measurement: "entities"
        icon: mdi:database-search
      - name: "RAG Last Indexed"
        unique_id: rag_last_indexed
        value_template: "{{ value_json.last_indexed }}"
        icon: mdi:clock-outline

# --- 2. Rebuild command --------------------------------------------------
rest_command:
  rag_rebuild:
    url: "http://localhost:8765/rag_rebuild"
    method: POST
    headers:
      X-Api-Key: "<your gateway api key>"
```

Restart HA once after adding these, then add a card to any dashboard:

```yaml
type: entities
title: RAG Index
entities:
  - entity: sensor.rag_index_entities
  - entity: sensor.rag_last_indexed
  - type: button
    name: Rebuild starten
    tap_action:
      action: perform-action
      perform_action: rest_command.rag_rebuild
      data: {}
```

When the rebuild finishes (takes 10–60 s depending on entity count and
embedding server speed) a **persistent notification** appears in the HA
bell menu showing the indexed entity count and timestamp. No manual
sensor refresh needed — the next automatic poll updates the sensor
values within 60 s.

### LLM Preprocessor

| Key | Default | Notes |
|-----|---------|-------|
| `preprocessor_enabled` | `true` | Extra LLM call that classifies intent, fixes typos/STT errors, and resolves pronouns before the main pipeline. |
| `preprocessor_url` | _(empty)_ | Leave empty to reuse `lmstudio_url`. |
| `preprocessor_api_key` | _(empty)_ | Leave empty to reuse `lmstudio_api_key`. |
| `preprocessor_model` | _(empty)_ | Leave empty to reuse `lmstudio_model`. A small fast model is recommended. |
| `preprocessor_timeout` | `30` | Seconds. |
| `preprocessor_temperature` | `0.1` | |

### Fallback

| Key | Default | Notes |
|-----|---------|-------|
| `fallback_mode` | `0` | 0 = off, 1 = REST (live HA states + retry parser), 2 = MCP (LM Studio + HA MCP tools). |
| `fallback_rest_max_entities` | `0` | 0 = no limit. Used by mode 1 to keep the prompt small. |
| `fallback_rest_domains` | `light,switch,...` | Comma-separated HA domains included in mode-1 fallback. |

### History

| Key | Default | Notes |
|-----|---------|-------|
| `history_size` | `0` | 0 = disabled. How many past user turns the LLM sees per chat. |
| `history_include_assistant` | `true` | Let the LLM see its own past replies. |
| `history_append_executions` | `false` | Append executed actions to history so follow-ups like "did it work?" have context. |

### Required fields

Nothing is required globally — every "required" field depends on which
services you enable. The add-on validates on startup and refuses to start
when something essential is missing:

| Field | Required when |
|-------|---------------|
| `telegram_bot_token` | `enable_telegram_bot` is on |
| `telegram_chat_id` (≠ 0) | `enable_telegram_bot` is on |
| `lmstudio_url` | `enable_voice_gateway` or `enable_telegram_bot` is on |

Pure example: if you only use `enable_notify_gateway` (HA → TTS / Telegram fan-out
without LLM commands), all three are optional.

Strongly recommended (warning only — feature degrades gracefully):

| Field | Effect when missing |
|-------|---------------------|
| `whisper_url` | Voice input (audio uploads, Telegram voice messages) unavailable; text still works |
| `ha_token` | Falls back to the supervisor token — only needed for external HA instances |

Auto-fallbacks (no warning):

- `rag_embed_url` empty → reuses `lmstudio_url`
- `preprocessor_url` / `preprocessor_model` / `preprocessor_api_key` empty → reuses corresponding `lmstudio_*`

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

- **"telegram_bot enabled but telegram_bot_token is empty"** — fill in
  `telegram_bot_token` and restart the add-on.
- **`HA_TOKEN` errors / 401 from HA** — leave `ha_token` blank to
  fall back to `SUPERVISOR_TOKEN`, or paste a long-lived access token.
- **Whisper returns empty transcripts** — check that `whisper_url` points at a
  running server and that the `language` setting matches your speech.

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
