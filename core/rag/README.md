# RAG Mode – Installation & Connection Verification

This file only covers how to **install** the embedding model and **verify** that the embedding endpoint responds. For architecture, workflow, examples, config reference and history behaviour, see [OVERVIEW.md](../../../../OVERVIEW.md).

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

The embedding model runs **alongside** your chat model. They can share the same LM Studio server or live on separate hosts (the bot has distinct `RAG_EMBED_URL` / `LMSTUDIO_URL` config entries).

| Purpose | Endpoint | Model type |
|---|---|---|
| Chat / LLM | `/v1/chat/completions` | Chat model (Qwen, etc.) |
| Embeddings | `/v1/embeddings` | Embedding model |

### Recommended model

`text-embedding-nomic-embed-text-v2-moe` — 768 dims, multilingual, good German understanding. Default in `.env`.

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

---

## Step 2 – Verify the embedding endpoint

Replace host, key and model with the values from your `.env`:

```bash
curl http://<RAG_EMBED_URL>/v1/embeddings \
  -H "Authorization: Bearer <RAG_EMBED_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-nomic-embed-text-v2-moe","input":"Licht Wohnzimmer an"}'
```

A working response:
```json
{"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.023, -0.017, ...]}],...}
```

The `embedding` array length must match `RAG_EMBED_DIM` in `.env` (768 for nomic-v2-moe).

Also confirm the model is actually loaded (not just downloaded):
```bash
curl http://<RAG_EMBED_URL>/api/v0/models \
  -H "Authorization: Bearer <RAG_EMBED_API_KEY>"
```
The embedding model entry must show `"state": "loaded"`.

---

## Step 3 – Build the index

Send `/rag_rebuild` in the Telegram chat. The bot pulls every HA entity, merges `userconfig/entities.yaml` overlay data, embeds everything in batches, and writes `data/rag/entities.sqlite`.

Typical runtime: **10–60 seconds** depending on entity count and embedding hardware.

**When to rebuild:**
- After adding new devices or integrations in HA
- After editing `userconfig/entities.yaml` (keywords, descriptions, actions override, meta)
- After switching `RAG_EMBED_MODEL` (DB is recreated automatically if embedding dim changes)

Rebuilding is upsert-based — existing rows are updated in place.

---

For everything else (how the workflow works, DB-entry examples, per-entity metadata, LLM prompt format, conversation history, full config reference) — see [OVERVIEW.md](../../../../OVERVIEW.md).
