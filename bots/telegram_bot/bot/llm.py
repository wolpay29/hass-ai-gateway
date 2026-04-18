import requests
import yaml
import json
import re
import logging
from pathlib import Path
from bot.config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    OLLAMA_TEMPERATURE, OLLAMA_NO_THINK
)

logger = logging.getLogger(__name__)


def _load_entities() -> list:
    path = Path(__file__).parent / "entities.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["entities"]


def parse_command(transcript: str) -> dict | None:
    entities = _load_entities()

    entity_list = "\n".join(
        f'- {e["id"]} | keywords: {", ".join(e.get("keywords", []))} | actions: {", ".join(e["actions"])}'
        for e in entities
    )

    system_prompt = f"""Smart Home Assistent. Antworte NUR mit JSON, kein anderer Text.

Geraete:
{entity_list}

Bei Treffer: {{"entity_id":"...", "action":"...", "domain":"..."}}
Kein Treffer: {{"entity_id":null, "action":null, "domain":null}}"""

    # Wenn NO_THINK in den Settings auf true steht, verbieten wir dem Modell das Denken
    if OLLAMA_NO_THINK:
        system_prompt += "\n\nWICHTIG: Antworte SOFORT und DIREKT. Verwende KEINE <think> Tags und führe keine Gedankengänge aus!"

    logger.info(f"[LLM] Transcript: '{transcript}'")
    logger.info(f"[LLM] Modell: {OLLAMA_MODEL} | Server: {OLLAMA_URL} | No-Think: {OLLAMA_NO_THINK}")

    try:
        endpoint = f"{OLLAMA_URL}/v1/chat/completions"
        
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript}
            ],
            "temperature": OLLAMA_TEMPERATURE
        }

        response = requests.post(
            endpoint,
            json=payload,
            timeout=OLLAMA_TIMEOUT
        )

        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.info(f"[LLM] Antwort raw: {content}")

        # Erstes vollstaendiges JSON-Objekt extrahieren (auch mehrzeilig)
        match = re.search(r'\{.*?\}', content, re.DOTALL)
        if not match:
            logger.error("[LLM] Kein JSON gefunden")
            return None

        result = json.loads(match.group())
        logger.info(f"[LLM] Parsed: {result}")
        return result if result.get("entity_id") else None

    except requests.exceptions.HTTPError as e:
        logger.error(f"[LLM] HTTP-Fehler: {e} - Response: {response.text}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[LLM] Fehler beim Parsen des JSONs: {e}")
        return None
    except Exception as e:
        logger.error(f"[LLM] Allgemeiner Fehler: {e}")
        return None