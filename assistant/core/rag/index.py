import logging
from pathlib import Path

import requests
import yaml

from core.config import (
    HA_URL, HA_TOKEN,
    RAG_DB_PATH, RAG_TOP_K, RAG_KEYWORD_BOOST, RAG_EMBED_DIM,
)
from core.rag import store
from core.rag.embeddings import embed, embed_one

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32  # texts per LM Studio embedding request

# Default action sets per HA domain. Used for entities that are NOT in
# entities.yaml. If an entity IS in entities.yaml, its yaml `actions` list
# overrides these defaults.
_DOMAIN_ACTIONS: dict[str, list[str]] = {
    "light":         ["turn_on", "turn_off", "toggle", "get_state"],
    "switch":        ["turn_on", "turn_off", "toggle", "get_state"],
    "automation":    ["trigger"],
    "sensor":        ["get_state"],
    "binary_sensor": ["get_state"],
    "climate":       ["get_state"],
    "cover":         ["turn_on", "turn_off", "get_state"],
    "input_boolean": ["turn_on", "turn_off", "toggle", "get_state"],
    "script":        ["turn_on"],
    "scene":         ["turn_on"],
    "button":        ["turn_on"],
    "media_player":  ["get_state"],
    "fan":           ["turn_on", "turn_off", "get_state"],
    "lock":          ["turn_on", "turn_off", "get_state"],
    "person":        ["get_state"],
    "weather":       ["get_state"],
    "device_tracker": ["get_state"],
    "sun":           ["get_state"],
    "zone":          ["get_state"],
    "group":         ["turn_on", "turn_off", "toggle", "get_state"],
}
_DEFAULT_ACTIONS = ["get_state"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_yaml_curated() -> dict:
    """Return {entity_id: entity_dict} from entities.yaml."""
    path = Path(__file__).parent.parent / "entities.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {e["id"]: e for e in (data or {}).get("entities", [])}


def _fetch_ha_states() -> list[dict]:
    """Fetch full /api/states. We keep `unit_of_measurement` for sensors
    which we use in the embed_text to help queries like 'wie viele kWh'."""
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    r = requests.get(f"{HA_URL}/api/states", headers=headers, timeout=15)
    r.raise_for_status()
    raw = r.json()

    out = []
    for s in raw:
        eid = s.get("entity_id", "")
        if "." not in eid:
            continue
        attrs = s.get("attributes", {}) or {}
        out.append({
            "entity_id": eid,
            "domain": eid.split(".", 1)[0],
            "friendly_name": attrs.get("friendly_name", ""),
            "unit": attrs.get("unit_of_measurement", ""),
        })
    return out


def _make_embed_text(
    entity_id: str,
    friendly_name: str,
    unit: str,
    curated_description: str,
    curated_keywords: list[str],
) -> str:
    """Build the text that gets embedded.

    Only fields relevant for RETRIEVAL go here:
      - entity_id (often contains meaningful tokens: 'pool_pump', 'licht_paul')
      - friendly_name (HA's human-readable name)
      - unit (helps queries like 'wie viele kWh' find sensors with kWh unit)
      - curated description + keywords (if entity is in entities.yaml)

    Domain, state and actions are NOT here — they are metadata for the LLM,
    not search signals.
    """
    parts = [entity_id]
    if friendly_name:
        parts.append(friendly_name)
    if unit:
        parts.append(unit)
    if curated_description:
        parts.append(curated_description)
    if curated_keywords:
        parts.append(" ".join(curated_keywords))
    return " | ".join(parts)


def _resolve_actions(domain: str, curated: dict | None) -> list[str]:
    """yaml actions override the domain default."""
    if curated and curated.get("actions"):
        return list(curated["actions"])
    return _DOMAIN_ACTIONS.get(domain, _DEFAULT_ACTIONS)


def _batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build() -> int:
    """Pull all HA entities, embed them, and write to the RAG index.

    Merges keywords, descriptions, actions and meta from entities.yaml for
    curated entities. Returns the number of indexed entities.
    """
    logger.info("[RAG Index] Starte Rebuild ...")

    curated = _load_yaml_curated()
    ha_entities = _fetch_ha_states()
    if not ha_entities:
        logger.error("[RAG Index] Keine Entities von HA erhalten")
        return 0

    logger.info(
        f"[RAG Index] {len(ha_entities)} Entities von HA | "
        f"{len(curated)} kurierte Eintraege aus entities.yaml"
    )

    records = []
    for ha in ha_entities:
        eid = ha["entity_id"]
        cur = curated.get(eid)

        curated_keywords = cur.get("keywords", []) if cur else []
        curated_description = cur.get("description", "") if cur else ""
        curated_meta = cur.get("meta", "") if cur else ""
        actions = _resolve_actions(ha["domain"], cur)

        friendly_name = curated_description or ha.get("friendly_name", "")

        records.append({
            "entity_id": eid,
            "friendly_name": friendly_name,
            "domain": ha["domain"],
            "actions": actions,
            "curated_keywords": curated_keywords,
            "curated_meta": curated_meta,
            "embed_text": _make_embed_text(
                entity_id=eid,
                friendly_name=ha.get("friendly_name", ""),
                unit=ha.get("unit", ""),
                curated_description=curated_description,
                curated_keywords=curated_keywords,
            ),
        })

    # Embed in batches to avoid hitting request size limits
    texts = [r["embed_text"] for r in records]
    embeddings: list[list[float]] = []
    total_batches = (len(texts) - 1) // _BATCH_SIZE + 1
    for i, batch in enumerate(_batched(texts, _BATCH_SIZE), start=1):
        logger.info(
            f"[RAG Index] Embedding Batch {i}/{total_batches} "
            f"({len(batch)} Texte) ..."
        )
        embeddings.extend(embed(batch))

    conn = store.get_connection(RAG_DB_PATH)
    try:
        store.init_db(conn, RAG_EMBED_DIM)
        for record, vec in zip(records, embeddings):
            store.upsert_entity(conn, record, vec)
        conn.commit()
    finally:
        conn.close()

    logger.info(
        f"[RAG Index] Rebuild abgeschlossen: {len(records)} Entities indiziert"
    )
    return len(records)


def query(transcript: str) -> list[dict]:
    """Find the most relevant HA entities for a natural-language transcript.

    Steps:
      1. Embed the transcript
      2. KNN search in sqlite-vec
      3. Apply keyword boost for curated entities whose keywords appear in the transcript
      4. Return the top RAG_TOP_K entities formatted for parse_command_rag()

    Returns an empty list if the index does not exist or an error occurs.
    """
    db_path = Path(RAG_DB_PATH)
    if not db_path.exists():
        logger.warning("[RAG Index] Datenbank nicht gefunden – bitte /rag_rebuild ausfuehren")
        return []

    conn = store.get_connection(RAG_DB_PATH)
    try:
        count = store.get_entity_count(conn)
        if count == 0:
            logger.warning("[RAG Index] Datenbank leer – bitte /rag_rebuild ausfuehren")
            return []

        query_vec = embed_one(transcript)
        results = store.search(conn, query_vec, RAG_TOP_K)
    finally:
        conn.close()

    # Keyword boost: curated keywords that literally appear in the transcript
    # get a lower effective distance (lower = closer = better).
    transcript_lower = transcript.lower()
    for r in results:
        kws = [k.strip().lower() for k in r.get("curated_keywords", "").split(",") if k.strip()]
        if kws and any(kw in transcript_lower for kw in kws):
            r["distance"] *= 1.0 - RAG_KEYWORD_BOOST

    results.sort(key=lambda x: x["distance"])

    logger.info(
        f"[RAG Index] Query '{transcript}' | "
        f"Top-{len(results)}: {[r['entity_id'] for r in results[:5]]}"
    )

    # Convert to the format that parse_command_rag() expects
    # (`distance` is included so callers can do confidence-based logic).
    return [
        {
            "entity_id": r["entity_id"],
            "friendly_name": r.get("friendly_name", ""),
            "domain": r.get("domain", ""),
            "actions": [a for a in r.get("actions", "").split(",") if a],
            "meta": r.get("curated_meta", ""),
            "distance": r.get("distance", 0.0),
        }
        for r in results
    ]


def status() -> dict:
    """Return index statistics for display in /rag_rebuild replies."""
    db_path = Path(RAG_DB_PATH)
    if not db_path.exists():
        return {"exists": False, "count": 0, "last_indexed": None}
    conn = store.get_connection(RAG_DB_PATH)
    try:
        return {
            "exists": True,
            "count": store.get_entity_count(conn),
            "last_indexed": store.get_last_indexed(conn),
        }
    finally:
        conn.close()
