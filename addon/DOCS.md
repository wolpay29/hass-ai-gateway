# Hass AI Gateway — Documentation

Three services in one container: `voice_gateway` (port 8765), `notify_gateway` (port 8766), `telegram_bot`.

---

## User-editable files

Editable via **File Editor** or **Samba** at `/addon_configs/<slug>/`. Defaults are seeded on first start.

| File | Purpose |
|------|---------|
| `userconfig/entities.yaml` | Entity catalogue for the parser and RAG index |
| `userconfig/entities_blacklist.yaml` | Entity-id patterns excluded from RAG |
| `userconfig/pre_llm_memory.md` | Hints injected before RAG (typo fixes, pronoun rules) |
| `userconfig/post_llm_memory.md` | Hints injected into every parser prompt |
| `menus.yaml` | Telegram bot menus and button actions |

After editing `entities.yaml`: send `/rag_rebuild` in Telegram or `POST /rag_rebuild` to the voice gateway.
After editing other files: restart the add-on.

### entities.yaml

```yaml
entities:
  - id: light.living_room
    description: "Living room light"
    keywords: ["living room", "lounge"]
    actions: ["turn_on", "turn_off", "toggle"]
    domain: light
    meta: ""

  - id: climate.living_room
    description: "Living room thermostat"
    keywords: ["living room heating", "thermostat"]
    actions: ["set_temperature", "set_hvac_mode"]
    domain: climate
    meta: ""
```

### entities_blacklist.yaml

```yaml
blacklist:
  - sensor.zigbee2mqtt_bridge_state
  - sensor.*_battery_level
  - automation.test_*
```

### pre_llm_memory.md / post_llm_memory.md

Free-text Markdown. Content inside `<!-- ... -->` is ignored.

- **pre** — injected before RAG (query rewriter). Use for STT corrections and pronoun rules.
- **post** — appended to every parser prompt. Use for preferences and never-do rules.

---

## Configuration

Settings are grouped into collapsible sections in the HA UI.

### Required fields

The add-on validates on startup and refuses to start if required fields are missing.

| Field | Required when |
|-------|---------------|
| `telegram.bot_token` | `services.telegram_bot` on |
| `telegram.chat_id` (≠ 0) | `services.telegram_bot` on |
| `lmstudio.url` | `services.voice_gateway` or `services.telegram_bot` on |

Blank `ha_token` → uses the auto-injected supervisor token (correct for most setups).
Blank `whisper.url` → voice input disabled, text commands still work.
Blank `rag.embed_url` → reuses `lmstudio.url`.
Blank `preprocessor.url/model/api_key` → reuses the corresponding `lmstudio.*` value.

### RAG

After a config change or entity update: trigger a rebuild via `/rag_rebuild` in Telegram or `POST /rag_rebuild` on the voice gateway.

The index lives at `/data/rag/entities.sqlite`.

#### RAG status + rebuild button in HA

Add to `configuration.yaml` (remove `headers:` if `voice_api_key` is empty):

```yaml
rest:
  - resource: "http://localhost:8765/rag_status"
    scan_interval: 60
    headers:
      X-Api-Key: "<your api key>"
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

rest_command:
  rag_rebuild:
    url: "http://localhost:8765/rag_rebuild"
    method: POST
    headers:
      X-Api-Key: "<your api key>"
```

Dashboard card:

```yaml
type: entities
title: RAG Index
entities:
  - entity: sensor.rag_index_entities
  - entity: sensor.rag_last_indexed
  - type: button
    name: Rebuild
    tap_action:
      action: perform-action
      perform_action: rest_command.rag_rebuild
      data: {}
```

---

## Calling the gateways from HA

### notify_gateway

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

### voice_gateway — text command

```yaml
rest_command:
  voice_gateway_text:
    url: "http://localhost:8765/text"
    method: POST
    content_type: "application/json"
    payload: '{"text": "{{ text }}", "device_id": "ha"}'
```

---

## Troubleshooting

- **bot_token empty** — fill in `telegram.bot_token` and restart.
- **401 from HA** — leave `ha_token` blank to use the supervisor token.
- **No transcription** — check `whisper.url` points at a running server and `language` matches your speech.
