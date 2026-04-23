import logging
import requests
from bot.config import (
    RAG_EMBED_URL, RAG_EMBED_API_KEY, RAG_EMBED_TIMEOUT, RAG_EMBED_MODEL,
)

logger = logging.getLogger(__name__)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via the RAG embedding host (/v1/embeddings).

    Returns vectors in the same order as the input list.
    Raises on HTTP or connection errors so callers can fall back.
    """
    headers = {"Content-Type": "application/json"}
    if RAG_EMBED_API_KEY:
        headers["Authorization"] = f"Bearer {RAG_EMBED_API_KEY}"

    payload = {"model": RAG_EMBED_MODEL, "input": texts}

    try:
        response = requests.post(
            f"{RAG_EMBED_URL}/v1/embeddings",
            json=payload,
            headers=headers,
            timeout=RAG_EMBED_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
    except Exception as e:
        logger.error(f"[RAG Embed] Fehler beim Embedding-Aufruf: {e}")
        raise


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
