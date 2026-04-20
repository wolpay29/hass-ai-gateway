import requests
import logging
from bot.config import (
    LMSTUDIO_URL, LMSTUDIO_MODEL, LMSTUDIO_API_KEY,
    LMSTUDIO_TIMEOUT, LMSTUDIO_TEMPERATURE,
    HA_URL, HA_TOKEN,
)

logger = logging.getLogger(__name__)


def fallback_via_mcp(transcript: str, chat_id: int = 0) -> str | None:
    """Fallback (Mode 2) ueber LM Studio mit HA-MCP-Server.

    Uebergibt den HA-MCP-Server als ephemeral integration direkt im API-Request,
    damit LM Studio die MCP-Tools kennt und aufrufen kann.

    Voraussetzungen in LM Studio:
    - Developer Tab -> Server laeuft auf 0.0.0.0:1234
    - Server Settings -> "Allow per-request MCPs" aktiviert
    - Server Settings -> API-Auth aktiviert, Key in LMSTUDIO_API_KEY
    - Ein Tool-faehiges Modell geladen (z.B. Qwen2.5-Instruct >=7B)
    """
    system = (
        "Du bist ein Home-Assistant-Assistent mit Zugriff auf MCP-Tools. "
        "Nutze die verfuegbaren Tools, um Geraete zu steuern oder Zustaende abzufragen. "
        "Antworte knapp, direkt und auf Deutsch, ohne Markdown."
    )

    payload = {
        "model": LMSTUDIO_MODEL,
        # /api/v1/chat erwartet "input" statt "messages" (LM Studio native Format)
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript},
        ],
        "temperature": LMSTUDIO_TEMPERATURE,
        # MCP-Server als ephemeral integration mitgeben — sonst kennt das Modell keine Tools.
        # Benoetigt "Allow per-request MCPs" in LM Studio Server Settings.
        "integrations": [
            {
                "type": "ephemeral_mcp",
                "server_label": "home-assistant",
                "server_url": f"{HA_URL}/api/mcp",
                "headers": {"Authorization": f"Bearer {HA_TOKEN}"},
            }
        ],
    }

    headers = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"

    logger.info(
        f"[LM Studio Fallback] Transcript: '{transcript}' | "
        f"MCP: {HA_URL}/api/mcp | Modell: {LMSTUDIO_MODEL}"
    )

    response = None
    try:
        # /api/v1/chat ist LM Studios nativer Endpunkt — nur dieser unterstuetzt
        # den "integrations" Parameter fuer MCP. /v1/chat/completions ignoriert ihn.
        response = requests.post(
            f"{LMSTUDIO_URL}/api/v1/chat",
            json=payload,
            headers=headers,
            timeout=LMSTUDIO_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        logger.debug(f"[LM Studio Fallback] Response keys: {list(data.keys())}")
        # /api/v1/chat gibt "output" zurueck; /v1/chat/completions gibt "choices"
        if "output" in data:
            # LM Studio native format: output ist eine Liste von message-Objekten
            output = data["output"]
            content = ""
            for item in (output if isinstance(output, list) else [output]):
                if isinstance(item, dict):
                    c = item.get("content") or ""
                    if isinstance(c, list):
                        c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                    content += c
            content = content.strip()
        else:
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
