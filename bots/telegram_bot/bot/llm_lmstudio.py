import requests
import logging
from bot.config import (
    LMSTUDIO_URL, LMSTUDIO_MODEL, LMSTUDIO_API_KEY,
    LMSTUDIO_TIMEOUT, LMSTUDIO_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def fallback_via_mcp(transcript: str, chat_id: int = 0) -> str | None:
    """Fallback (Mode 2) ueber LM Studio mit konfiguriertem HA-MCP-Server.

    Voraussetzungen (vom Nutzer einzurichten):
    - LM Studio laeuft und Server ist aktiviert (Developer Tab).
    - %USERPROFILE%\\.lmstudio\\mcp.json enthaelt den HA-MCP-Server inkl.
      "Authorization: Bearer <Long-Lived Access Token>".
    - LM Studio Server-Auth ist aktiviert; API-Key steht in LMSTUDIO_API_KEY.
    - Ein Tool-faehiges Modell ist geladen.

    LM Studio entscheidet intern, welche MCP-Tools aufgerufen werden; wir sehen
    nur den finalen Antworttext. Entity-Whitelisting und Ausfuehrung laufen
    vollstaendig auf HA-/LM-Studio-Seite.
    """
    system = (
        "Du bist ein Home-Assistant-Assistent mit Zugriff auf MCP-Tools. "
        "Nutze die verfuegbaren Tools, um Geraete zu steuern oder Zustaende abzufragen. "
        "Antworte knapp, direkt und auf Deutsch, ohne Markdown."
    )

    payload = {
        "model": LMSTUDIO_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript},
        ],
        "temperature": LMSTUDIO_TEMPERATURE,
    }

    headers = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"

    logger.info(
        f"[LM Studio Fallback] Transcript: '{transcript}' | "
        f"Server: {LMSTUDIO_URL} | Modell: {LMSTUDIO_MODEL} | "
        f"Auth: {'ja' if LMSTUDIO_API_KEY else 'nein'}"
    )

    response = None
    try:
        response = requests.post(
            f"{LMSTUDIO_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=LMSTUDIO_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        content = (data["choices"][0]["message"].get("content") or "").strip()
        logger.info(f"[LM Studio Fallback] Antwort: {content[:200]}")
        return content or None
    except requests.exceptions.HTTPError as e:
        body = response.text if response is not None else ""
        logger.error(f"[LM Studio Fallback] HTTP-Fehler: {e} - Body: {body}")
        return None
    except Exception as e:
        logger.error(f"[LM Studio Fallback] Fehler: {e}")
        return None
