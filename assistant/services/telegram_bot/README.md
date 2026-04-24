# Telegram Home Assistant Bot

Telegram bot for Home Assistant control with menu-based actions, battery monitoring, and optional voice-message transcription via Faster Whisper.

## What it does

- Shows a persistent Telegram main menu with submenus for gate and pool control.
- Reads the current battery SOC and PV surplus from Home Assistant.
- Sends a notification when the battery level is above a configured threshold.
- Lets you quickly turn on the pool heating with a button via Home Assistant automations.
- Downloads Telegram voice messages and transcribes them (local Faster Whisper or external API).
- Accepts free-form voice/text commands and routes them to Home Assistant via an LLM (LM Studio).
- Optional **RAG mode**: indexes all HA entities in a local sqlite-vec DB and uses semantic retrieval instead of sending the full entity list to the LLM on every request.
- **Conversation history** (both modes): resolves anaphoric follow-ups like "und wieder aus", "auch beim Max", "und jetzt?".
- Three-tier fallback: curated entity whitelist → live REST list → MCP server with tool use.

## Key files

- `telegram_ha_bot.py`  
  Main bot code.

- `bot/voice.py`  
  Voice download directory handling and Faster Whisper transcription.

- `bot/config.py`  
  Loads environment variables and application settings.

- `bot/handlers.py` / `bot/llm.py`  
  Command dispatch, conversation history, RAG enrichment, LLM calls, fallback routing.

- `bot/rag/`  
  RAG subsystem: `embeddings.py` (HTTP client), `store.py` (sqlite-vec wrapper), `index.py` (build/query). See [bot/rag/README.md](bot/rag/README.md) for embedding-model install.

- `bot/entities.yaml`  
  Curated entity whitelist — keywords, descriptions, per-entity action overrides, free-text meta hints.

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

Copy `assistant/.env.example` to `assistant/.env` and fill in your values. The full reference is in the `.env.example` file and the [Full config reference](#full-config-reference) section below. Minimum required entries:

```ini
BOT_TOKEN=your-telegram-bot-token
MY_CHAT_ID=123456789

HA_URL=http://192.168.1.x:8123
HA_TOKEN=your-long-lived-ha-token

# Whisper: "external" = use the faster-whisper Docker (recommended)
WHISPER_BACKEND=external
WHISPER_EXTERNAL_URL=http://192.168.1.x:10300/v1/audio/transcriptions
WHISPER_EXTERNAL_MODEL=deepdml/faster-whisper-large-v3-turbo-ct2

# LM Studio
LMSTUDIO_URL=http://192.168.1.x:1234
LMSTUDIO_MODEL=qwen2.5-7b-instruct
LMSTUDIO_API_KEY=sk-...

# Fallback: 0=off, 1=REST, 2=MCP
FALLBACK_MODE=2
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

## RAG mode

When `RAG_ENABLED=true`, the bot replaces the "send the whole `entities.yaml` to the LLM" step with a semantic-search step:

1. **Embed** the user's transcript into a vector (LM Studio `/v1/embeddings`).
2. **KNN-search** a local SQLite database (`sqlite-vec`) that contains **every** HA entity (pulled from `/api/states`) plus merged metadata from `entities.yaml` for curated ones.
3. **Boost** results whose curated keywords literally appear in the transcript.
4. Send **only the top `RAG_TOP_K` candidates** (default 15) to the LLM. Each candidate carries its own per-entity `actions` list, so the LLM no longer needs generic domain rules.
5. If the LLM returns `needs_fallback` or no actions, the normal `FALLBACK_MODE` kicks in exactly as before.

The legacy path (`RAG_ENABLED=false`) is fully unchanged.

For embedding-model installation and endpoint verification, see [bot/rag/README.md](bot/rag/README.md).

### Workflow

#### RAG disabled (`RAG_ENABLED=false`) — legacy, unchanged

```
User message (text or voice)
        │
        ▼  (voice only)
   Whisper transcription
        │
        ▼
   entities.yaml → LLM
        │                               │
        ▼ found clean action            ▼ no match / needs_fallback
   Execute in HA                  FALLBACK_MODE:
                                    0 → error message
                                    1 → pull ALL states from HA REST → LLM
                                    2 → LM Studio + HA MCP server
```

#### RAG enabled (`RAG_ENABLED=true`)

```
User message (text or voice)
        │
        ▼  (voice only)
   Whisper transcription
        │
        ▼
   Embed transcript → RAG_EMBED_URL /v1/embeddings
        │
        ▼
   KNN search in local SQLite (sqlite-vec)
   → top RAG_TOP_K candidates (default 15)
        │
        ▼
   Keyword boost (yaml keywords appearing in transcript)
        │
        ▼
   LLM gets those ~15 entities, each with its own actions list
        │                               │
        ▼ found clean action            ▼ needs_fallback / no actions
   Execute in HA                  FALLBACK_MODE (unchanged)
```

### Key differences at a glance

| | Legacy | RAG |
|---|---|---|
| First LLM prompt contains | All curated entities from yaml | Top `RAG_TOP_K` candidates from the DB |
| Finds non-curated entities | Only via fallback REST pull | Already in the first step (whole HA is indexed) |
| Extra step | None | 1 embedding call |
| Per-entity actions | Generic domain rules in the prompt | Explicit per-entity `actions` list |
| `entities.yaml` role | Sole source of truth | Optional overlay: keywords, description, action overrides, hints |
| Fallback modes (0/1/2) | Active | Active |

### Architecture: embed_text vs. metadata

Each DB row has two conceptually different text fields:

| Field | Purpose | Used by |
|---|---|---|
| `embed_text` | Everything that helps **retrieval** (find the right row from a natural-language query) | sqlite-vec KNN |
| metadata (`friendly_name`, `domain`, `actions`, `curated_meta`) | Everything the **LLM** needs to decide what to call | LLM prompt after retrieval |

**`embed_text` content:**
```
<entity_id> | <friendly_name> | <unit> | <curated_description> | <curated_keywords>
```

- `entity_id` usually contains meaningful tokens (`pool_pump`, `licht_paul`, `trigger_rollo_paul_auf`).
- `friendly_name` = HA's human-readable name.
- `unit` = only for sensors (e.g. `kWh`, `°C`) — helps queries like *"wie viele kWh hat die PV heute gemacht"*.
- `curated_description` + `curated_keywords` = only present if the entity exists in `entities.yaml`.

Domain, state and actions are **not** in `embed_text`. State is volatile, actions are not a search signal, domain alone is useless.

**Metadata fields:**

| Field | Source | Example |
|---|---|---|
| `entity_id` | HA | `light.licht_paul` |
| `friendly_name` | yaml description (preferred) or HA friendly_name | `Licht Pauls Zimmer` |
| `domain` | HA | `light` |
| `actions` | yaml `actions` override, else domain default | `[turn_on, turn_off, toggle, get_state]` |
| `curated_meta` | yaml `meta` (free text hint, optional) | `Nur turn_on verfuegbar — turn_off ignoriert HA` |

### Domain → default actions

Used when the entity is **not** in `entities.yaml`. If an entity has a yaml `actions` list, that list wins.

| Domain | Default actions |
|---|---|
| `light`, `switch`, `input_boolean`, `group` | `turn_on, turn_off, toggle, get_state` |
| `cover`, `fan`, `lock` | `turn_on, turn_off, get_state` |
| `automation` | `trigger` |
| `script`, `scene`, `button` | `turn_on` |
| `sensor`, `binary_sensor`, `climate`, `media_player`, `person`, `weather`, `device_tracker`, `sun`, `zone` | `get_state` |

Anything else falls back to `[get_state]`.

### Example DB entries

**Curated light (in entities.yaml):**
```yaml
- id: light.licht_paul
  domain: light
  description: "Licht Pauls Zimmer"
  keywords: ["paul", "pauls zimmer", "paul licht"]
  actions: [turn_on, turn_off, toggle, get_state]
  meta: ""
```
```
entity_id:        light.licht_paul
friendly_name:    Licht Pauls Zimmer       ← from yaml description
domain:           light
actions:          turn_on,turn_off,toggle,get_state
curated_keywords: paul,pauls zimmer,paul licht
curated_meta:     ""
embed_text:       light.licht_paul | Licht Paul | Licht Pauls Zimmer | paul pauls zimmer paul licht
```

**Curated switch with partial functionality (rollo):**
```yaml
- id: switch.rollo_paul_auf
  domain: switch
  description: "Rollo Paul rauf"
  keywords: ["rollo paul auf", "rollo paul hoch", "rollo paul rauf"]
  actions: [turn_on]
  meta: "Nur turn_on verfuegbar — turn_off ignoriert HA"
```
```
entity_id:        switch.rollo_paul_auf
friendly_name:    Rollo Paul rauf
domain:           switch
actions:          turn_on                  ← yaml override
curated_keywords: rollo paul auf,rollo paul hoch,rollo paul rauf
curated_meta:     Nur turn_on verfuegbar — turn_off ignoriert HA
embed_text:       switch.rollo_paul_auf | Rollo Paul rauf | Rollo Paul rauf | rollo paul auf rollo paul hoch rollo paul rauf
```

**Curated automation:**
```yaml
- id: automation.trigger_pool_pump_on
  domain: automation
  description: "Pool Pumpe einschalten"
  keywords: ["pool an", "pool pumpe an"]
  actions: [trigger]
  meta: ""
```
```
entity_id:        automation.trigger_pool_pump_on
friendly_name:    Pool Pumpe einschalten
domain:           automation
actions:          trigger
curated_keywords: pool an,pool pumpe an
curated_meta:     ""
embed_text:       automation.trigger_pool_pump_on | Pool Pumpe | Pool Pumpe einschalten | pool an pool pumpe an
```

**Non-curated sensor with a unit:**
```
entity_id:        sensor.wohnzimmer_temperature
friendly_name:    Wohnzimmer Temperatur
domain:           sensor
actions:          get_state
curated_keywords: ""
curated_meta:     ""
embed_text:       sensor.wohnzimmer_temperature | Wohnzimmer Temperatur | °C
```

Non-curated entities are fully retrievable via embedding (entity_id + friendly_name + unit is usually enough), they just don't get the keyword boost or the free-text hint.

### What the LLM sees after RAG retrieval

For the transcript *"Licht bei Paul an"*, KNN returns ~15 candidates, keyword boost pushes `light.licht_paul` up, and the LLM receives:

```
- light.licht_paul | name: Licht Pauls Zimmer | actions: turn_on, turn_off, toggle, get_state
- light.wohnzimmer_deckenlicht | name: Deckenlicht Wohnzimmer | actions: turn_on, turn_off, toggle, get_state
- switch.rollo_paul_auf | name: Rollo Paul rauf | actions: turn_on | note: Nur turn_on verfuegbar — turn_off ignoriert HA
- automation.trigger_licht_paul_szene | name: Licht-Szene Paul | actions: trigger
- ... (up to RAG_TOP_K)
```

The LLM returns:
```json
{"reply": "Licht in Pauls Zimmer wird eingeschaltet.",
 "actions": [{"domain":"light","action":"turn_on","entity_id":"light.licht_paul"}]}
```

Parameterised requests return `needs_fallback` and hand off to `FALLBACK_MODE`:
```json
{"reply":"","actions":[{"action":"needs_fallback","entity_id":"switch.rollo_paul_auf"}]}
```

### How entities.yaml keywords are used

- **At index time:** yaml `description` and `keywords` are appended to `embed_text`. Even a query using a yaml alias will match semantically.
- **At query time:** after KNN, if any yaml keyword of a candidate literally appears in the transcript, its distance is multiplied by `(1 - RAG_KEYWORD_BOOST)`. Exact alias matches rank first even when semantic scores are close.

Example: `light.licht_paul` has keywords `["paul", "pauls zimmer"]`. Transcript *"Licht bei Paul an"* → `paul` matches → `distance *= 0.7` → this entity ranks first.

### RAG fallback behaviour

Failures that transparently fall back to the legacy `entities.yaml` → LLM path:
- RAG DB file missing / empty (before first `/rag_rebuild`).
- Embedding call fails (LM Studio down, wrong model).

Failures that hand off to `FALLBACK_MODE`:
- RAG returned candidates, but the LLM replied `needs_fallback` (parameterized action).
- RAG returned candidates, but the LLM returned an empty action list.

## Conversation history & anaphoric follow-ups

The bot keeps a per-chat rolling history of the last `LLM_HISTORY_SIZE` turn pairs. This works **in both RAG=true and RAG=false modes** — it's shared infrastructure, not RAG-specific.

History does two things:

1. **LLM context** — history is passed to the chat-completion call as prior `user`/`assistant` messages so the LLM can resolve pronouns ("und wieder aus", "bei beiden", "auch beim Max").
2. **RAG embed enrichment** (RAG mode only) — if the current transcript is ≤5 words, the stored user messages and (optionally) assistant replies + execution summaries are prepended to the embed query so KNN finds the entities the conversation is about.

### How each history param affects behaviour

- `LLM_HISTORY_SIZE=0` → history disabled. Every turn is stateless. Follow-ups like "und wieder aus" will not work.
- `HISTORY_INCLUDE_ASSISTANT=false` → only user turns stored. The LLM sees what you asked, but not what it said. Weaker.
- `HISTORY_INCLUDE_ASSISTANT=true` (default) → user + assistant turns stored. Full context.
- `HISTORY_APPEND_EXECUTIONS=true` → after execution, `ausgefuehrt: turn_on -> light.licht_paul, ...` is appended to the stored assistant turn. The LLM sees exactly which entity IDs were controlled (not just what it intended in its `reply`). In RAG mode these IDs also feed the embed query on the next short follow-up.

### Example 1 — chained commands

With `LLM_HISTORY_SIZE=4`, `HISTORY_INCLUDE_ASSISTANT=true`, `HISTORY_APPEND_EXECUTIONS=true`, RAG enabled:

```
User:     Schalt das licht beim paul ein
Bot:      Ich schalte das Licht im Zimmer von Paul ein.
          ✅ turn_on -> light.licht_paul

User:     Beim max auch
Bot:      Ich schalte auch das Licht im Zimmer von Max ein.
          ✅ turn_on -> light.licht_max

User:     Bei beiden aus
Bot:      Ich schalte die Lichter im Zimmer von Paul und Max aus.
          ✅ turn_off -> light.licht_paul
          ✅ turn_off -> light.licht_max

User:     Und wieder an
Bot:      Ich schalte die Lichter im Zimmer von Paul und Max wieder ein.
          ✅ turn_on -> light.licht_paul
          ✅ turn_on -> light.licht_max
```

**Under the hood on "Und wieder an"** (3 words → enrichment triggers):

Stored history (simplified):
```
user:      "Schalt das licht beim paul ein"
assistant: '{"reply":"...Paul...","actions":[...]}\nausgefuehrt: turn_on -> light.licht_paul'
user:      "Beim max auch"
assistant: '{"reply":"...Max...","actions":[...]}\nausgefuehrt: turn_on -> light.licht_max'
user:      "Bei beiden aus"
assistant: '{"reply":"...Paul und Max...","actions":[...]}\nausgefuehrt: turn_off -> light.licht_paul, turn_off -> light.licht_max'
```

Enriched embed query:
```
Schalt das licht beim paul ein | Beim max auch | Bei beiden aus
| Ich schalte das Licht im Zimmer von Paul ein.
| ausgefuehrt: turn_on -> light.licht_paul
| Ich schalte auch das Licht im Zimmer von Max ein.
| ausgefuehrt: turn_on -> light.licht_max
| Ich schalte die Lichter im Zimmer von Paul und Max aus.
| ausgefuehrt: turn_off -> light.licht_paul, turn_off -> light.licht_max
→ Und wieder an
```

RAG retrieves both `light.licht_paul` and `light.licht_max` as top candidates. The LLM, seeing the same history in its chat messages, resolves "und wieder an" to both entities and returns two `turn_on` actions.

### Example 2 — state query follow-ups

```
User:     Welche stellung hat die rollo vom paul
Bot:      Die Rollo von Paul steht auf 0,0 %.
          ✅ get_state -> input_number.rollo_position_paul

User:     Und jetzt?
Bot:      Das Rollo ist bei 5,8 %.
          ✅ get_state -> input_number.rollo_position_paul
```

"Und jetzt?" is 2 words → enrichment kicks in. The enriched embed query contains the previous transcript, the assistant reply ("Die Rollo von Paul..."), and the execution summary (`ausgefuehrt: get_state -> input_number.rollo_position_paul`) — so RAG retrieves the same entity, the LLM sees it in history, and the state is re-fetched with the current live value.

## Build / rebuild the RAG index

Send `/rag_rebuild` in the Telegram chat. The bot pulls every HA entity, merges `entities.yaml` overlay data, embeds everything in batches, and writes `data/rag/entities.sqlite`. Typical runtime: 10–60 seconds.

Rebuild after adding new HA devices, editing `entities.yaml`, or switching embedding models (dim change recreates the DB).

## Full config reference

### Core

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Telegram bot token |
| `MY_CHAT_ID` | — | Numeric Telegram chat ID for notifications |
| `HA_URL` / `HA_TOKEN` | — | Home Assistant URL and long-lived token |
| `CHECK_INTERVAL_SECONDS` | `300` | Battery-check interval |
| `BATTERY_THRESHOLD` | `80` | Notify when battery SOC ≥ this value |

### Whisper (voice transcription)

| Variable | Default | Description |
|---|---|---|
| `WHISPER_BACKEND` | `local` | `local` or `external` |
| `WHISPER_MODEL` | `small` | Faster-Whisper model size (local only) |
| `WHISPER_DEVICE` | `cpu` | `cpu` / `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantisation |
| `WHISPER_LANGUAGE` | `de` | Forced language (empty = auto) |
| `WHISPER_EXTERNAL_URL` | — | External Whisper API endpoint |
| `WHISPER_EXTERNAL_MODEL` | — | External Whisper model name |
| `VOICE_REPLY_WITH_TRANSCRIPT` | `true` | Reply with the transcript before processing |
| `VOICE_DOWNLOAD_DIR` | `data/voice` | Where to store downloaded voice files |

### LM Studio / LLM

| Variable | Default | Description |
|---|---|---|
| `LMSTUDIO_URL` | — | Chat model host |
| `LMSTUDIO_MODEL` | — | Chat model identifier |
| `LMSTUDIO_API_KEY` | — | Bearer token |
| `LMSTUDIO_TIMEOUT` | `30` | HTTP timeout (s) |
| `LMSTUDIO_TEMPERATURE` | `0.1` | LLM sampling temperature |
| `LMSTUDIO_TOP_P` / `LMSTUDIO_TOP_K` | `0.9` / `20` | LLM sampling |
| `LMSTUDIO_NUM_CTX` | `2048` | Context window for the primary prompt |
| `LMSTUDIO_NO_THINK` | `true` | Suppress `<think>` tags in output |
| `LMSTUDIO_CONTEXT_LENGTH` | `8000` | Context for Mode 2 (`/api/v1/chat` with MCP) |
| `LMSTUDIO_MCP_ALLOWED_TOOLS` | whitelist | HA MCP tool filter for Mode 2 |
| `MAX_ACTIONS_PER_COMMAND` | `0` | Hard cap on actions per command (0 = unlimited) |

### Conversation history (universal — affects both RAG=true and RAG=false)

| Variable | Default | Description |
|---|---|---|
| `LLM_HISTORY_SIZE` | `0` | Number of prior user+assistant pairs kept per chat. `0` disables history. |
| `HISTORY_INCLUDE_ASSISTANT` | `true` | Store assistant turns. When `false`, only user messages are kept and the LLM does not remember its own prior replies. In RAG mode also used for embed-query enrichment. |
| `HISTORY_APPEND_EXECUTIONS` | `false` | After each execution, append `"ausgefuehrt: turn_on -> light.licht_paul, ..."` to the stored assistant turn. Gives explicit `entity_id` signal to the LLM and (in RAG mode) the embed query. Requires `HISTORY_INCLUDE_ASSISTANT=true`. |

### RAG-specific

| Variable | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch for RAG mode |
| `RAG_DB_PATH` | `data/rag/entities.sqlite` | Path to the SQLite DB |
| `RAG_TOP_K` | `15` | Candidates retrieved per query |
| `RAG_KEYWORD_BOOST` | `0.3` | Distance multiplier reduction when a yaml keyword matches |
| `RAG_EMBED_URL` | = `LMSTUDIO_URL` | Embedding host (can differ from chat host) |
| `RAG_EMBED_API_KEY` | = `LMSTUDIO_API_KEY` | Auth for the embedding host |
| `RAG_EMBED_TIMEOUT` | = `LMSTUDIO_TIMEOUT` | HTTP timeout for embedding requests |
| `RAG_EMBED_MODEL` | `text-embedding-nomic-embed-text-v2-moe` | Model name |
| `RAG_EMBED_DIM` | `768` | Must match the model's output dim |

### Fallback

| Variable | Default | Description |
|---|---|---|
| `FALLBACK_MODE` | `0` | `0`=off, `1`=REST, `2`=MCP |
| `FALLBACK_REST_DOMAINS` | (list) | Domain filter for Mode 1 (empty / `{}` / `[]` = all) |
| `FALLBACK_REST_MAX_ENTITIES` | `0` | Cap for Mode 1 (0 = no limit) |

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

### v0.4.0 (2026-04-23)

- Added **RAG mode** (`RAG_ENABLED`): sqlite-vec-backed semantic retrieval over every HA entity; per-entity `actions` lists in the LLM prompt; optional `entities.yaml` overlay for keywords, descriptions, action overrides and meta hints.
- Added `/rag_rebuild` command — pulls all HA entities, merges yaml overlay, embeds in batches, writes `data/rag/entities.sqlite`.
- Added separate embedding-host config (`RAG_EMBED_URL`, `RAG_EMBED_API_KEY`, `RAG_EMBED_TIMEOUT`) — embedding model can run on a different LM Studio instance than the chat model.
- Added keyword boost (`RAG_KEYWORD_BOOST`): yaml keywords appearing literally in the transcript reduce KNN distance.
- Added **universal conversation history** (both RAG modes): `LLM_HISTORY_SIZE`, `HISTORY_INCLUDE_ASSISTANT`, `HISTORY_APPEND_EXECUTIONS`. Resolves anaphoric follow-ups ("und wieder aus", "bei beiden", "und jetzt?") via LLM chat context and — in RAG mode — embed-query enrichment for short transcripts (≤5 words).
- RAG failures (DB missing, embedding endpoint down) transparently fall back to the legacy `entities.yaml` path; `needs_fallback` / empty actions still hand off to `FALLBACK_MODE`.

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