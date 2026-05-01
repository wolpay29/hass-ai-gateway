import logging
import sqlite3
import struct
from pathlib import Path

import sqlite_vec

logger = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db(conn: sqlite3.Connection, embed_dim: int):
    """Create tables. Drops and recreates the vector table if embed_dim changed."""
    embed_dim = int(embed_dim)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id        TEXT PRIMARY KEY,
            friendly_name    TEXT,
            domain           TEXT,
            actions          TEXT,
            curated_keywords TEXT,
            curated_meta     TEXT,
            embed_text       TEXT,
            indexed_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    stored = conn.execute("SELECT value FROM meta WHERE key='embed_dim'").fetchone()
    if stored and int(stored[0]) != embed_dim:
        logger.warning(
            f"[RAG Store] Embedding-Dimension geaendert "
            f"({stored[0]} -> {embed_dim}). Vektortabelle wird neu erstellt."
        )
        conn.execute("DROP TABLE IF EXISTS entity_vecs")

    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS entity_vecs USING vec0(
            embedding float[{embed_dim}]
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('embed_dim', ?)",
        (str(embed_dim),),
    )
    conn.commit()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def upsert_entity(conn: sqlite3.Connection, entity: dict, embedding: list[float]):
    """Upsert one entity + its vector.

    Expected keys in `entity`:
        entity_id, friendly_name, domain, actions (list[str]),
        curated_keywords (list[str]), curated_meta (str), embed_text (str)
    """
    conn.execute(
        """
        INSERT INTO entities
            (entity_id, friendly_name, domain, actions,
             curated_keywords, curated_meta, embed_text, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(entity_id) DO UPDATE SET
            friendly_name    = excluded.friendly_name,
            domain           = excluded.domain,
            actions          = excluded.actions,
            curated_keywords = excluded.curated_keywords,
            curated_meta     = excluded.curated_meta,
            embed_text       = excluded.embed_text,
            indexed_at       = excluded.indexed_at
        """,
        (
            entity["entity_id"],
            entity.get("friendly_name", ""),
            entity.get("domain", ""),
            ",".join(entity.get("actions", [])),
            ",".join(entity.get("curated_keywords", [])),
            entity.get("curated_meta", ""),
            entity.get("embed_text", ""),
        ),
    )
    rowid = conn.execute(
        "SELECT rowid FROM entities WHERE entity_id = ?", (entity["entity_id"],)
    ).fetchone()[0]

    # vec0 requires delete-before-insert for updates
    conn.execute("DELETE FROM entity_vecs WHERE rowid = ?", (rowid,))
    conn.execute(
        "INSERT INTO entity_vecs(rowid, embedding) VALUES (?, ?)",
        (rowid, _pack(embedding)),
    )


def search(conn: sqlite3.Connection, query_vec: list[float], k: int) -> list[dict]:
    vec_rows = conn.execute(
        """
        SELECT rowid, distance FROM entity_vecs
        WHERE embedding MATCH ?
        AND k = ?
        ORDER BY distance
        """,
        (_pack(query_vec), k),
    ).fetchall()

    results = []
    for row in vec_rows:
        entity = conn.execute(
            "SELECT * FROM entities WHERE rowid = ?", (row["rowid"],)
        ).fetchone()
        if entity:
            results.append({**dict(entity), "distance": row["distance"]})
    return results


def lookup_by_entity_ids(conn: sqlite3.Connection, entity_ids: list[str]) -> list[dict]:
    """Return entity records for the given entity_ids."""
    if not entity_ids:
        return []
    placeholders = ",".join("?" * len(entity_ids))
    rows = conn.execute(
        f"SELECT * FROM entities WHERE entity_id IN ({placeholders})",
        entity_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def get_entity_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]


def get_last_indexed(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(indexed_at) FROM entities").fetchone()
    return row[0] if row else None
