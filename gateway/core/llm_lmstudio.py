import requests
import logging
from core.config import (
    LMSTUDIO_URL, LMSTUDIO_MODEL, LMSTUDIO_API_KEY,
    LMSTUDIO_TIMEOUT, LMSTUDIO_TEMPERATURE,
    LMSTUDIO_MCP_ALLOWED_TOOLS, LMSTUDIO_CONTEXT_LENGTH,
    HA_URL, HA_TOKEN,
)

logger = logging.getLogger(__name__)


def fallback_via_mcp(transcript: str, chat_id: int = 0) -> str | None:
    """Fallback (Mode 2) ueber LM Studio mit HA-MCP-Server.

    Nutzt LM Studios nativen /api/v1/chat-Endpunkt mit ephemeral_mcp integration —
    nur dort werden MCP-Tools aus dem Request geladen und aufgerufen.

    Voraussetzungen in LM Studio:
    - Developer Tab -> Server laeuft auf 0.0.0.0:1234
    - Server Settings -> "Allow per-request MCPs" aktiviert
    - Server Settings -> API-Auth aktiviert, Key in LMSTUDIO_API_KEY
    - Ein Tool-faehiges Modell geladen (z.B. Qwen >=7B)
    """
    mcp_url = f"{HA_URL}/api/mcp"

    integration = {
        "type": "ephemeral_mcp",
        "server_label": "home-assistant",
        "server_url": mcp_url,
        "headers": {"Authorization": f"Bearer {HA_TOKEN}"},
    }
    if LMSTUDIO_MCP_ALLOWED_TOOLS:
        integration["allowed_tools"] = LMSTUDIO_MCP_ALLOWED_TOOLS

    payload = {
        "model": LMSTUDIO_MODEL,
        # /api/v1/chat akzeptiert "input" als String (einfachster Fall —
        # matched den funktionierenden curl-Test des Users).
        "input": transcript,
        "temperature": LMSTUDIO_TEMPERATURE,
        "context_length": LMSTUDIO_CONTEXT_LENGTH,
        # MCP-Server als ephemeral integration mitgeben — sonst kennt das Modell keine Tools.
        # Benoetigt "Allow per-request MCPs" in LM Studio Server Settings.
        "integrations": [integration],
    }

    headers = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"

    logger.info(
        f"[Fallback Mode 2 / MCP] chat={chat_id} | Transcript: '{transcript}' | "
        f"MCP: {mcp_url} | Modell: {LMSTUDIO_MODEL} | "
        f"allowed_tools: {LMSTUDIO_MCP_ALLOWED_TOOLS or 'ALL'} | ctx={LMSTUDIO_CONTEXT_LENGTH}"
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

        # Output ist eine Liste mit items type={message|reasoning|tool_call}.
        # Fuer den User interessieren nur die "message"-Items; tool_calls und
        # reasoning loggen wir zur Nachvollziehbarkeit.
        output = data.get("output", [])
        if not isinstance(output, list):
            output = [output]

        message_parts: list[str] = []
        tool_calls: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "message":
                c = item.get("content") or ""
                if isinstance(c, list):
                    c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                message_parts.append(c)
            elif itype == "tool_call":
                tool_calls.append(str(item.get("tool", "?")))

        stats = data.get("stats", {})
        logger.info(
            f"[Fallback Mode 2 / MCP] tool_calls={tool_calls or '[]'} | "
            f"input_tokens={stats.get('input_tokens')} | "
            f"output_tokens={stats.get('total_output_tokens')}"
        )

        content = "".join(message_parts).strip()
        if not content and "choices" in data:
            # Fallback auf OpenAI-Format, falls LM Studio Version das anders liefert
            content = (data["choices"][0]["message"].get("content") or "").strip()

        if content:
            logger.info(f"[Fallback Mode 2 / MCP] Antwort: {content[:200]}")
            return content

        logger.warning("[Fallback Mode 2 / MCP] Leere Antwort vom Modell")
        return None

    except requests.exceptions.HTTPError as e:
        body = response.text if response is not None else ""
        logger.error(f"[Fallback Mode 2 / MCP] HTTP-Fehler: {e} - Body: {body}")
        return None
    except Exception as e:
        logger.error(f"[Fallback Mode 2 / MCP] Fehler: {e}")
        return None
