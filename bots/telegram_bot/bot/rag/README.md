# RAG Mode – Telegram HA Bot

## What this is

When `RAG_ENABLED=true`, the bot replaces the "send the whole `entities.yaml` to the LLM" step with a semantic-search step:

1. **Embed** the user's transcript into a vector using an embedding model (LM Studio `/v1/embeddings`).
2. **KNN-search** a local SQLite database (`sqlite-vec`) that contains **every** HA entity (pulled from `/api/states`) plus merged metadata from `entities.yaml` for curated ones.
3. **Boost** results whose curated keywords literally appear in the transcript.
4. Send **only the top `RAG_TOP_K` candidates** (default 15) to the LLM. Each candidate carries its own `actions` list, so the LLM no longer needs generic domain rules.
5. If the LLM returns `needs_fallback` or no actions, the normal `FALLBACK_MODE` (0 / 1 / 2) kicks in exactly as before.

The legacy path (`RAG_ENABLED=false`) is fully unchanged.

---

## Complete bot workflow

### RAG disabled (`RAG_ENABLED=false`) — legacy, fully unchanged

```
User message (text or voice)
        │
        ▼  (voice only)
   Whisper transcription
        │
        ▼
   entities.yaml → LLM
   "Here are all curated entities, what does the user want?"
        │                               │
        ▼ found clean action            ▼ no match / needs_fallback
   Execute in HA                  FALLBACK_MODE:
                                    0 → error message
                                    1 → pull ALL states from HA REST → LLM
                                    2 → LM Studio + HA MCP server
```

### RAG enabled (`RAG_ENABLED=true`) — new first step

```
User message (text or voice)
        │
        ▼  (voice only)
   Whisper transcription
        │
        ▼
   Embed transcript
   → /v1/embeddings on RAG_EMBED_URL (embedding model)
        │
        ▼
   KNN search in local SQLite (sqlite-vec)
   → returns top RAG_TOP_K closest entities (default 15)
        │
        ▼
   Keyword boost
   (entities.yaml keywords that appear literally in the transcript
    are pushed higher in the ranking)
        │
        ▼
   LLM gets only those ~15 entities, each with its own actions list
   "Here are the most likely candidates, what does the user want?"
        │                               │
        ▼ found clean action            ▼ needs_fallback / no actions
   Execute in HA                  FALLBACK_MODE (unchanged):
                                    0 → error message
                                    1 → pull ALL states from HA REST → LLM
                                    2 → LM Studio + HA MCP server
```

### Key differences at a glance

| | Legacy | RAG |
|---|---|---|
| First LLM prompt contains | All curated entities from yaml | Top `RAG_TOP_K` candidates from the DB |
| Finds non-curated entities | Only via fallback REST pull | Already in the first step (whole HA is indexed) |
| Extra step | None | 1 embedding call |
| Per-entity actions | Generic domain rules in the prompt | Explicit per-entity `actions` list |
| `entities.yaml` role | Sole source of truth | Optional overlay: adds keywords, description, action overrides, hints |
| Fallback modes (0/1/2) | Active | Active |

---

## Architecture: embed_text vs. metadata

Each DB row has two conceptually different text fields:

| Field | Purpose | Used by |
|---|---|---|
| `embed_text` | Everything that helps **retrieval** (find the right row from a natural-language query) | sqlite-vec KNN |
| metadata (`friendly_name`, `domain`, `actions`, `curated_meta`) | Everything the **LLM** needs to decide what to call | LLM prompt after retrieval |

### `embed_text` content

```
<entity_id> | <friendly_name> | <unit> | <curated_description> | <curated_keywords>
```

- `entity_id` usually contains meaningful tokens (`pool_pump`, `licht_paul`, `trigger_rollo_paul_auf`).
- `friendly_name` = HA's human-readable name.
- `unit` = only for sensors (e.g. `kWh`, `°C`) — helps queries like *"wie viele kWh hat die PV heute gemacht"* match sensors with `kWh` unit.
- `curated_description` + `curated_keywords` = only present if the entity exists in `entities.yaml`.

Domain, state and actions are **not** in `embed_text`. State is volatile, actions are not a search signal, domain alone is useless.

### Metadata fields

| Field | Source | Example |
|---|---|---|
| `entity_id` | HA | `light.licht_paul` |
| `friendly_name` | yaml description (preferred) or HA friendly_name | `Licht Pauls Zimmer` |
| `domain` | HA | `light` |
| `actions` | yaml `actions` override, else domain default (see table below) | `[turn_on, turn_off, toggle, get_state]` |
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

---

## Example DB entries

### Curated light (in entities.yaml)

`entities.yaml` entry:
```yaml
- id: light.licht_paul
  domain: light
  description: "Licht Pauls Zimmer"
  keywords: ["paul", "pauls zimmer", "paul licht"]
  actions: [turn_on, turn_off, toggle, get_state]
  meta: ""
```

Stored DB row:
```
entity_id:        light.licht_paul
friendly_name:    Licht Pauls Zimmer       ← from yaml description
domain:           light
actions:          turn_on,turn_off,toggle,get_state
curated_keywords: paul,pauls zimmer,paul licht
curated_meta:     ""
embed_text:       light.licht_paul | Licht Paul | Licht Pauls Zimmer | paul pauls zimmer paul licht
```

### Curated switch with partial functionality (rollo)

```yaml
- id: switch.rollo_paul_auf
  domain: switch
  description: "Rollo Paul rauf"
  keywords: ["rollo paul auf", "rollo paul hoch", "rollo paul rauf"]
  actions: [turn_on]
  meta: "Nur turn_on verfuegbar — turn_off ignoriert HA"
```

Stored DB row:
```
entity_id:        switch.rollo_paul_auf
friendly_name:    Rollo Paul rauf
domain:           switch
actions:          turn_on                  ← yaml override, no turn_off/toggle
curated_keywords: rollo paul auf,rollo paul hoch,rollo paul rauf
curated_meta:     Nur turn_on verfuegbar — turn_off ignoriert HA
embed_text:       switch.rollo_paul_auf | Rollo Paul rauf | Rollo Paul rauf | rollo paul auf rollo paul hoch rollo paul rauf
```

### Curated automation

```yaml
- id: automation.trigger_pool_pump_on
  domain: automation
  description: "Pool Pumpe einschalten"
  keywords: ["pool an", "pool pumpe an", "pool pumpe einschalten"]
  actions: [trigger]
  meta: ""
```

Stored DB row:
```
entity_id:        automation.trigger_pool_pump_on
friendly_name:    Pool Pumpe einschalten
domain:           automation
actions:          trigger
curated_keywords: pool an,pool pumpe an,pool pumpe einschalten
curated_meta:     ""
embed_text:       automation.trigger_pool_pump_on | Pool Pumpe | Pool Pumpe einschalten | pool an pool pumpe an pool pumpe einschalten
```

### Curated sensor

```yaml
- id: sensor.sn_3015651602_pv_power
  domain: sensor
  description: "Aktuelle PV-Leistung"
  keywords: ["pv leistung", "solarleistung", "wie viel strom"]
  actions: [get_state]
  meta: ""
```

Stored DB row:
```
entity_id:        sensor.sn_3015651602_pv_power
friendly_name:    Aktuelle PV-Leistung
domain:           sensor
actions:          get_state
curated_keywords: pv leistung,solarleistung,wie viel strom
curated_meta:     ""
embed_text:       sensor.sn_3015651602_pv_power | PV Power | W | Aktuelle PV-Leistung | pv leistung solarleistung wie viel strom
```

### Non-curated entities (only in HA, not in entities.yaml)

A random switch that exists in HA but has no yaml entry:
```
entity_id:        switch.kitchen_coffee_machine
friendly_name:    Kaffeemaschine Kueche     ← from HA friendly_name
domain:           switch
actions:          turn_on,turn_off,toggle,get_state   ← domain default
curated_keywords: ""
curated_meta:     ""
embed_text:       switch.kitchen_coffee_machine | Kaffeemaschine Kueche
```

A random sensor with a unit:
```
entity_id:        sensor.wohnzimmer_temperature
friendly_name:    Wohnzimmer Temperatur
domain:           sensor
actions:          get_state
curated_keywords: ""
curated_meta:     ""
embed_text:       sensor.wohnzimmer_temperature | Wohnzimmer Temperatur | °C
```

Both are fully retrievable by the embedding (entity_id + friendly_name + unit is usually enough for German queries), they just don't get the keyword boost or the free-text hint.

---

## What the LLM sees after RAG retrieval

For the transcript *"Licht bei Paul an"*, sqlite-vec returns ~15 candidates, the keyword boost pushes `light.licht_paul` up, and the LLM receives something like:

```
Verfuegbare Entities:
- light.licht_paul | name: Licht Pauls Zimmer | actions: turn_on, turn_off, toggle, get_state
- light.wohnzimmer_deckenlicht | name: Deckenlicht Wohnzimmer | actions: turn_on, turn_off, toggle, get_state
- switch.rollo_paul_auf | name: Rollo Paul rauf | actions: turn_on | note: Nur turn_on verfuegbar — turn_off ignoriert HA
- switch.rollo_paul_ab | name: Rollo Paul runter | actions: turn_on | note: Nur turn_on verfuegbar — turn_off ignoriert HA
- automation.trigger_licht_paul_szene | name: Licht-Szene Paul | actions: trigger
- ... (up to RAG_TOP_K)
```

The LLM replies with the standard JSON action format:
```json
{
  "reply": "Licht in Pauls Zimmer wird eingeschaltet.",
  "actions": [
    {"domain": "light", "action": "turn_on", "entity_id": "light.licht_paul"}
  ]
}
```

If no candidate fits (e.g. the user said *"Rollo Paul auf 50 %"* and the switch cannot take a parameter), the LLM returns `needs_fallback`:
```json
{
  "reply": "",
  "actions": [{"action": "needs_fallback", "entity_id": "switch.rollo_paul_auf"}]
}
```
…and the bot hands off to `FALLBACK_MODE` 1 or 2 as configured.

---

## File structure

```
bot/rag/
  __init__.py       empty package marker
  embeddings.py     HTTP client for /v1/embeddings (RAG_EMBED_URL)
  store.py          sqlite-vec wrapper (schema, upsert, KNN search)
  index.py          build / rebuild / query logic
  README.md         this file

data/rag/
  entities.sqlite   created automatically on first /rag_rebuild
```

---

## Step 1 – Load an embedding model in LM Studio

The embedding model runs **alongside** your existing chat model. They share the same LM Studio server port but respond to different endpoints:

| Purpose | Endpoint | Model type |
|---|---|---|
| Chat / LLM | `/v1/chat/completions` | Chat model (Qwen, etc.) |
| Embeddings | `/v1/embeddings` | Embedding model |

### Recommended model

`text-embedding-nomic-embed-text-v2-moe` — 768 dims, explicitly multilingual, good German understanding. This is the default `RAG_EMBED_MODEL` in `.env`.

Alternatives:

| Model | Dims | Notes |
|---|---|---|
| `nomic-embed-text-v1.5` | 768 | English-first, works passably in German |
| `multilingual-e5-small` | 384 | Smallest multilingual option |

### How to load in LM Studio

1. Open LM Studio → **Search / Discover** tab.
2. Search for `text-embedding-nomic-embed-text-v2-moe`.
3. Download the GGUF Q8_0 variant if available.
4. Go to the **Developer** tab (`</>` icon).
5. Add the embedding model as a second loaded model on the same server. LM Studio routes `/v1/embeddings` to it automatically.

### Verify the embedding model works

```bash
curl http://10.1.10.78:1234/v1/embeddings \
  -H "Authorization: Bearer <RAG_EMBED_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-nomic-embed-text-v2-moe","input":"Licht Wohnzimmer an"}'
```

A working response:
```json
{"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.023,...]}],...}
```

The `embedding` array length must match `RAG_EMBED_DIM` in `.env` (768 for nomic-v2-moe).

---

## Step 2 – Configure .env

```ini
# --- RAG mode ---
RAG_ENABLED=true

# Local SQLite DB (created automatically)
RAG_DB_PATH=data/rag/entities.sqlite

# How many candidates to retrieve per query
RAG_TOP_K=15

# Effective-distance multiplier when a curated keyword appears literally
# 0.3 = reduce distance by 30 %
RAG_KEYWORD_BOOST=0.3

# Embedding host — defaults to the chat LM Studio if left empty.
# Separate entries so you can host embeddings on a different machine/port.
RAG_EMBED_URL=http://10.1.10.78:1234
RAG_EMBED_API_KEY=sk-lm-...
RAG_EMBED_TIMEOUT=30

# Model name as shown in LM Studio
RAG_EMBED_MODEL=text-embedding-nomic-embed-text-v2-moe

# Must match the model's output dim
RAG_EMBED_DIM=768
```

To switch back to legacy mode: set `RAG_ENABLED=false`. All other RAG vars are ignored.

---

## Step 3 – Build the index

Send `/rag_rebuild` in the Telegram chat.

The bot will:
1. Pull **every** entity from Home Assistant (`/api/states`, no filter).
2. For each entity also in `entities.yaml`, merge the curated `description`, `keywords`, `actions` override and `meta` hint.
3. Build `embed_text` per entity (retrieval text only).
4. Embed in batches of 32 via `RAG_EMBED_URL/v1/embeddings`.
5. Upsert rows into `data/rag/entities.sqlite` (vector + metadata).
6. Reply with the entity count and timestamp.

Typical runtime: **10–60 seconds** depending on entity count and embedding hardware.

### When to rebuild

- After adding new devices or integrations in HA.
- After editing `entities.yaml` (keywords, descriptions, actions override, meta).
- After switching `RAG_EMBED_MODEL` (the DB is recreated automatically if the embedding dim changes).

Rebuilding is **upsert-based**: existing rows are updated in place, so you can run it anytime.

---

## How entities.yaml keywords are used

At **index time**: yaml `description` and `keywords` are appended to `embed_text`. Even if the user uses an alias you defined in yaml, the embedding will match that entity semantically.

At **query time**: after KNN, if any yaml keyword of a candidate appears literally in the transcript, its distance is multiplied by `(1 - RAG_KEYWORD_BOOST)`. Exact alias matches rank first even when semantic scores are close.

Example:
- `light.licht_paul` has keywords `["paul", "pauls zimmer"]`.
- Transcript: *"Licht bei Paul an"*.
- The word `paul` matches → `distance *= 0.7` → this entity is first.

---

## Fallback behaviour

Failures that trigger the legacy path transparently:
- RAG DB file missing / empty (before first `/rag_rebuild`) → legacy `entities.yaml` → LLM path.
- Embedding call fails (LM Studio down, wrong model) → legacy path.

Failures that hand off to `FALLBACK_MODE`:
- RAG returned candidates, but the LLM replied `needs_fallback` (parameterized action, e.g. set temperature).
- RAG returned candidates, but the LLM returned an empty action list.

`FALLBACK_MODE` values:

| Value | Behaviour |
|---|---|
| `0` | Error message returned |
| `1` | Live REST pull from HA, all entities sent to LLM |
| `2` | LM Studio + HA MCP server (handles parameterized actions) |

---

## Config reference

| Variable | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch for RAG mode |
| `RAG_DB_PATH` | `data/rag/entities.sqlite` | Path to the SQLite DB |
| `RAG_TOP_K` | `15` | Candidates retrieved per query |
| `RAG_KEYWORD_BOOST` | `0.3` | Distance multiplier reduction when a yaml keyword matches |
| `RAG_EMBED_URL` | = `LMSTUDIO_URL` | Embedding host (can differ from chat host) |
| `RAG_EMBED_API_KEY` | = `LMSTUDIO_API_KEY` | Auth for the embedding host |
| `RAG_EMBED_TIMEOUT` | = `LMSTUDIO_TIMEOUT` | HTTP timeout for embedding requests (seconds) |
| `RAG_EMBED_MODEL` | `text-embedding-nomic-embed-text-v2-moe` | Model name sent in the request body |
| `RAG_EMBED_DIM` | `768` | Must match the model's output dimension |
