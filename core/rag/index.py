import fnmatch
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import requests
import yaml

from core.config import (
    HA_URL, HA_TOKEN,
    RAG_DB_PATH, RAG_TOP_K, RAG_KEYWORD_BOOST, RAG_DISTANCE_THRESHOLD, RAG_EMBED_DIM,
    USERCONFIG_DIR,
)
from core.rag import store
from core.rag.embeddings import embed, embed_one

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32  # texts per LM Studio embedding request

# Default action sets per HA domain. Used for entities that are NOT in
# entities.yaml. If an entity IS in entities.yaml, its yaml `actions` list
# overrides these defaults.
#
# Reine Read-Only-Domains (sensor, weather, ...) listen keine Actions: das LLM
# bekommt deren aktuelle States ohnehin direkt im RAG-Prompt und beantwortet
# Statusfragen aus diesen Werten — eine separate get_state-Action gibt es nicht
# mehr. Schaltbare Domains behalten ihre Actions.
_DOMAIN_ACTIONS: dict[str, list[str]] = {
    "light":         ["turn_on", "turn_off", "toggle"],
    "switch":        ["turn_on", "turn_off", "toggle"],
    "automation":    ["trigger"],
    "sensor":        [],
    "binary_sensor": [],
    "climate":       ["set_temperature", "set_hvac_mode"],
    "cover":         ["turn_on", "turn_off", "set_cover_position"],
    "input_boolean": ["turn_on", "turn_off", "toggle"],
    "script":        ["turn_on"],
    "scene":         ["turn_on"],
    "button":        ["turn_on"],
    "media_player":  ["turn_on", "turn_off"],
    "fan":           ["turn_on", "turn_off", "set_percentage"],
    "lock":          ["turn_on", "turn_off"],
    "person":        [],
    "weather":       [],
    "device_tracker": [],
    "sun":           [],
    "zone":          [],
    "group":         ["turn_on", "turn_off", "toggle"],
}
_DEFAULT_ACTIONS: list[str] = []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_yaml_curated() -> dict:
    """Return {entity_id: entity_dict} from entities.yaml."""
    path = USERCONFIG_DIR / "entities.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    #return {e["id"]: e for e in (data or {}).get("entities", [])}
    return {e["id"]: e for e in (data or {}).get("entities") or []}
    #                                                         ^^^^^ statt , []


def _load_blacklist() -> list[str]:
    """Return the list of entity_id patterns from entities_blacklist.yaml.

    Each pattern is either an exact entity_id or a Unix-style glob (fnmatch).
    Missing file or empty list -> no entities excluded.
    """
    path = USERCONFIG_DIR / "entities_blacklist.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("blacklist") or []
    return [str(p).strip() for p in raw if p and str(p).strip()]


def _is_blacklisted(entity_id: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(entity_id, p) for p in patterns)


def _fetch_area_mapping() -> dict[str, str]:
    """Build {entity_id: area_name} from HA's area + device + entity registries.

    Returns an empty dict when no areas are configured, the registries are not
    reachable, or the token lacks permission. The build path treats an empty
    mapping as "no area info available" and proceeds normally — entities just
    end up without an explicit area annotation, exactly like before.
    """
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    def _get(path: str) -> list[dict]:
        try:
            r = requests.get(f"{HA_URL}{path}", headers=headers, timeout=15)
            if r.status_code != 200:
                logger.warning(f"[RAG Index] {path} -> HTTP {r.status_code}, area data skipped")
                return []
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[RAG Index] {path} fehlgeschlagen ({e}), area data skipped")
            return []

    areas = _get("/api/config/area_registry")
    if not areas:
        return {}
    area_id_to_name: dict[str, str] = {
        a["area_id"]: a.get("name") or a["area_id"]
        for a in areas if a.get("area_id")
    }

    devices = _get("/api/config/device_registry")
    device_id_to_area: dict[str, str] = {}
    for d in devices:
        did = d.get("id")
        aid = d.get("area_id")
        if did and aid and aid in area_id_to_name:
            device_id_to_area[did] = area_id_to_name[aid]

    entities = _get("/api/config/entity_registry")
    mapping: dict[str, str] = {}
    for e in entities:
        eid = e.get("entity_id")
        if not eid:
            continue
        aid = e.get("area_id")
        if aid and aid in area_id_to_name:
            mapping[eid] = area_id_to_name[aid]
            continue
        did = e.get("device_id")
        if did and did in device_id_to_area:
            mapping[eid] = device_id_to_area[did]

    logger.info(
        f"[RAG Index] Area-Mapping: {len(area_id_to_name)} Areas, "
        f"{len(mapping)} Entities mit Area-Zuweisung"
    )
    return mapping


def _fetch_ha_states() -> list[dict]:
    """Fetch full /api/states. We keep `unit_of_measurement` for sensors
    which we use in the embed_text to help queries like 'wie viele kWh'.

    We also resolve each entity's area (if any) via the HA area/device/entity
    registries. Entities without an area get area="" and behave exactly like
    before — area is purely additive."""
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    r = requests.get(f"{HA_URL}/api/states", headers=headers, timeout=15)
    r.raise_for_status()
    raw = r.json()

    area_map = _fetch_area_mapping()

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
            "area": area_map.get(eid, ""),
        })
    return out


def _make_embed_text(
    entity_id: str,
    friendly_name: str,
    unit: str,
    area: str,
    curated_description: str,
    curated_keywords: list[str],
) -> str:
    """Build the text that gets embedded.

    Only fields relevant for RETRIEVAL go here:
      - entity_id (often contains meaningful tokens: 'pool_pump', 'licht_paul')
      - friendly_name (HA's human-readable name)
      - unit (helps queries like 'wie viele kWh' find sensors with kWh unit)
      - area (HA-configured room/area name, when available)
      - curated description + keywords (if entity is in entities.yaml)

    Area is appended only when set — entities without a configured area keep
    the exact same embed text as before, so retrieval doesn't regress for
    setups that rely on the entity_id/friendly_name carrying the room.

    Domain, state and actions are NOT here — they are metadata for the LLM,
    not search signals.
    """
    parts = [entity_id]
    if friendly_name:
        parts.append(friendly_name)
    if unit:
        parts.append(unit)
    if area:
        parts.append(area)
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
    blacklist = _load_blacklist()
    ha_entities = _fetch_ha_states()
    if not ha_entities:
        logger.error("[RAG Index] Keine Entities von HA erhalten")
        return 0

    excluded = [e for e in ha_entities if _is_blacklisted(e["entity_id"], blacklist)]
    if excluded:
        logger.info(
            f"[RAG Index] Blacklist filtert {len(excluded)} Entities raus "
            f"(z.B. {[e['entity_id'] for e in excluded[:5]]})"
        )
        ha_entities = [e for e in ha_entities if not _is_blacklisted(e["entity_id"], blacklist)]

    logger.info(
        f"[RAG Index] {len(ha_entities)} Entities von HA | "
        f"{len(curated)} kurierte Eintraege aus entities.yaml | "
        f"{len(blacklist)} Blacklist-Pattern"
    )

    records = []
    for ha in ha_entities:
        eid = ha["entity_id"]
        cur = curated.get(eid)

        curated_keywords = cur.get("keywords", []) if cur else []
        curated_description = cur.get("description", "") if cur else ""
        curated_meta_user = cur.get("meta", "") if cur else ""
        actions = _resolve_actions(ha["domain"], cur)
        area = ha.get("area", "")

        # Combine area into meta so the LLM sees it as a `note: ...` line.
        # Area first (when present), then user-curated meta. If neither is
        # set, the field stays empty — exactly like before.
        meta_parts: list[str] = []
        if area:
            meta_parts.append(f"Area: {area}")
        if curated_meta_user:
            meta_parts.append(curated_meta_user)
        combined_meta = " | ".join(meta_parts)

        friendly_name = curated_description or ha.get("friendly_name", "")

        records.append({
            "entity_id": eid,
            "friendly_name": friendly_name,
            "domain": ha["domain"],
            "actions": actions,
            "curated_keywords": curated_keywords,
            "curated_meta": combined_meta,
            "area": area,
            "embed_text": _make_embed_text(
                entity_id=eid,
                friendly_name=ha.get("friendly_name", ""),
                unit=ha.get("unit", ""),
                area=area,
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

    _write_rebuild_report(records, blacklist=blacklist, excluded=excluded)

    logger.info(
        f"[RAG Index] Rebuild abgeschlossen: {len(records)} Entities indiziert"
    )
    return len(records)


def _write_rebuild_report(records: list[dict], blacklist: list[str], excluded: list[dict]) -> None:
    """Write a human-readable + JSON snapshot of the freshly built index.

    Both files land next to the SQLite DB (`RAG_DB_PATH`):
      - rag_rebuild_report.md   — Markdown overview, easy to skim by hand
      - rag_rebuild_report.json — same data structured, easy to diff / parse

    Lists every indexed entity with the exact `embed_text` fed to the embedder
    and the `meta` (note) the LLM will see at query time, plus the source
    fields they were built from. Overwritten on every rebuild.
    """
    db_dir = Path(RAG_DB_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    md_path = db_dir / "rag_rebuild_report.md"
    json_path = db_dir / "rag_rebuild_report.json"
    timestamp = datetime.now().isoformat(timespec="seconds")

    with_area = sum(1 for r in records if r.get("area"))
    with_meta = sum(1 for r in records if r.get("curated_meta"))
    with_keywords = sum(1 for r in records if r.get("curated_keywords"))

    payload = {
        "generated_at": timestamp,
        "summary": {
            "indexed": len(records),
            "with_area": with_area,
            "with_curated_meta": with_meta,
            "with_curated_keywords": with_keywords,
            "blacklist_patterns": len(blacklist),
            "blacklisted_entities": [e["entity_id"] for e in excluded],
        },
        "entities": [
            {
                "entity_id": r["entity_id"],
                "domain": r["domain"],
                "friendly_name": r["friendly_name"],
                "area": r.get("area", ""),
                "actions": r.get("actions", []),
                "curated_keywords": r.get("curated_keywords", []),
                "meta_for_llm": r.get("curated_meta", ""),
                "embed_text": r.get("embed_text", ""),
            }
            for r in sorted(records, key=lambda x: (x["domain"], x["entity_id"]))
        ],
    }

    try:
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[RAG Index] Konnte JSON-Report nicht schreiben: {e}")

    lines: list[str] = []
    lines.append(f"# RAG Rebuild Report")
    lines.append("")
    lines.append(f"_Generated: {timestamp}_")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Indexed entities: **{len(records)}**")
    lines.append(f"- With HA area assigned: **{with_area}**")
    lines.append(f"- With curated meta (note): **{with_meta}**")
    lines.append(f"- With curated keywords: **{with_keywords}**")
    lines.append(f"- Blacklist patterns: **{len(blacklist)}**")
    if excluded:
        lines.append(f"- Blacklisted (excluded from index): {len(excluded)}")
        for e in excluded:
            lines.append(f"  - `{e['entity_id']}`")
    lines.append("")
    lines.append("## Entities")
    lines.append("")
    lines.append("Per entity: what was used to build the embed text (search signal) and the meta the LLM sees at query time.")
    lines.append("")

    for r in sorted(records, key=lambda x: (x["domain"], x["entity_id"])):
        lines.append(f"### `{r['entity_id']}`")
        lines.append("")
        lines.append(f"- **friendly_name**: {r['friendly_name'] or '_(none)_'}")
        lines.append(f"- **domain**: {r['domain']}")
        lines.append(f"- **area**: {r.get('area') or '_(none)_'}")
        actions = r.get("actions", []) or []
        lines.append(f"- **actions**: {', '.join(actions) if actions else '_(none)_'}")
        kws = r.get("curated_keywords", []) or []
        lines.append(f"- **curated_keywords**: {', '.join(kws) if kws else '_(none)_'}")
        lines.append(f"- **meta (LLM sees as `note:`)**: {r.get('curated_meta') or '_(none)_'}")
        lines.append(f"- **embed_text (used for retrieval)**: `{r.get('embed_text', '')}`")
        lines.append("")

    try:
        md_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[RAG Index] Report geschrieben: {md_path} und {json_path}")
    except Exception as e:
        logger.warning(f"[RAG Index] Konnte Markdown-Report nicht schreiben: {e}")


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
    # get a lower effective distance (lower = closer = better). Word-boundary
    # match so short keywords like "an" don't accidentally match "Banane".
    transcript_lower = transcript.lower()
    for r in results:
        kws = [k.strip().lower() for k in r.get("curated_keywords", "").split(",") if k.strip()]
        if kws and any(re.search(rf"\b{re.escape(kw)}\b", transcript_lower) for kw in kws):
            r["distance"] *= 1.0 - RAG_KEYWORD_BOOST

    results.sort(key=lambda x: x["distance"])

    pre_filter_count = len(results)
    if RAG_DISTANCE_THRESHOLD > 0 and results:
        best = results[0]
        filtered = [r for r in results if r["distance"] <= RAG_DISTANCE_THRESHOLD]
        if not filtered:
            filtered = [best]   # safety net - best candidate stays even when over threshold
        results = filtered

    top_with_dist = [(r['entity_id'], round(r['distance'], 3)) for r in results[:5]]
    logger.info(
        f"[RAG Index] Query '{transcript}' | "
        f"{pre_filter_count} -> {len(results)} (threshold={RAG_DISTANCE_THRESHOLD}) | "
        f"Top-5: {top_with_dist}"
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


def lookup_by_ids(entity_ids: list[str]) -> list[dict]:
    """Return entities by exact ID — used to augment RAG results with history context.

    Returns them in the same format as query() so they can be merged into the
    candidates list without any conversion on the caller side.
    """
    if not entity_ids:
        return []
    db_path = Path(RAG_DB_PATH)
    if not db_path.exists():
        return []
    conn = store.get_connection(RAG_DB_PATH)
    try:
        rows = store.lookup_by_entity_ids(conn, entity_ids)
    finally:
        conn.close()
    return [
        {
            "entity_id": r["entity_id"],
            "friendly_name": r.get("friendly_name", ""),
            "domain": r.get("domain", ""),
            "actions": [a for a in (r.get("actions") or "").split(",") if a],
            "meta": r.get("curated_meta", ""),
            "distance": 0.0,
        }
        for r in rows
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


if __name__ == "__main__":
    # CLI entry point: `python -m core.rag.index`
    # Inside the addon container: `docker exec addon_<slug> python -m core.rag.index`
    logging.basicConfig(
        format="%(asctime)s [rag-cli] %(levelname)s %(message)s",
        level=logging.INFO,
    )
    count = build()
    info = status()
    print(f"RAG-Index Rebuild abgeschlossen: {count} Entities indiziert")
    print(f"Zuletzt indiziert: {info.get('last_indexed', '?')}")
