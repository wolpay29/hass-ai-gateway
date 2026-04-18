import requests
import yaml
import json
import re
import logging
from pathlib import Path
from bot.config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    OLLAMA_TEMPERATURE, OLLAMA_NO_THINK, LLM_HISTORY_SIZE
)

logger = logging.getLogger(__name__)

# Gesprächsverlauf pro chat_id — nur aktiv wenn LLM_HISTORY_SIZE > 0
_history: dict[int, list] = {}


def _load_entities() -> list:
    path = Path(__file__).parent / "entities.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["entities"]


def parse_command(transcript: str, chat_id: int = 0) -> dict | None:
    entities = _load_entities()
    valid_ids = {e["id"] for e in entities}

    entity_list = "\n".join(
        f'- {e["id"]} | keywords: {", ".join(e.get("keywords", []))} | actions: {", ".join(e["actions"])}'
        for e in entities
    )

    system_prompt = f"""Smart Home Assistent. Antworte NUR mit JSON, kein anderer Text.

Geraete:
{entity_list}

Bei Treffer: {{"reply":"...", "entity_id":"...", "action":"...", "domain":"..."}}
Kein Treffer: {{"reply":"...", "entity_id":null, "action":null, "domain":null}}

WICHTIG: entity_id MUSS exakt aus der obigen Geräteliste stammen. Niemals eine entity_id erfinden!
"reply" ist immer eine kurze freundliche Antwort auf Deutsch."""

    if OLLAMA_NO_THINK:
        system_prompt += "\n\nWICHTIG: Antworte SOFORT und DIREKT. Verwende KEINE <think> Tags und führe keine Gedankengänge aus!"

    logger.info(f"[LLM] Transcript: '{transcript}'")
    logger.info(f"[LLM] Modell: {OLLAMA_MODEL} | Server: {OLLAMA_URL} | History: {LLM_HISTORY_SIZE}")

    # History aufbauen (nur wenn aktiviert)
    history = []
    if LLM_HISTORY_SIZE > 0 and chat_id != 0:
        history = _history.get(chat_id, [])

    try:
        endpoint = f"{OLLAMA_URL}/v1/chat/completions"

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": transcript}
            ],
            "temperature": OLLAMA_TEMPERATURE
        }

        response = requests.post(endpoint, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.info(f"[LLM] Antwort raw: {content}")

        match = re.search(r'\{.*?\}', content, re.DOTALL)
        if not match:
            logger.error("[LLM] Kein JSON gefunden")
            return None

        result = json.loads(match.group())
        logger.info(f"[LLM] Parsed: {result}")

        # entity_id gegen entities.yaml validieren — keine Halluzinationen erlaubt
        if result.get("entity_id") and result["entity_id"] not in valid_ids:
            logger.warning(f"[LLM] Halluzinierte Entity '{result['entity_id']}' – wird ignoriert")
            result["entity_id"] = None
            result["action"] = None
            result["domain"] = None

        # History speichern (nur wenn aktiviert)
        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            history.append({"role": "assistant", "content": content})
            # Auf max. Länge kürzen (je 2 Einträge pro Austausch)
            max_entries = LLM_HISTORY_SIZE * 2
            if len(history) > max_entries:
                history = history[-max_entries:]
            _history[chat_id] = history
            logger.info(f"[LLM] History für chat {chat_id}: {len(history)//2} Austausche gespeichert")

        return result

    except requests.exceptions.HTTPError as e:
        logger.error(f"[LLM] HTTP-Fehler: {e} - Response: {response.text}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[LLM] Fehler beim Parsen des JSONs: {e}")
        return None
    except Exception as e:
        logger.error(f"[LLM] Allgemeiner Fehler: {e}")
        return None