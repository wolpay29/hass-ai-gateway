import requests
import logging
from bot.config import HA_URL, HA_TOKEN

logger = logging.getLogger(__name__)


def call_service(domain: str, action: str, entity_id: str) -> bool:
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    # Automations nutzen "trigger" statt turn_on/off
    service = "trigger" if action == "trigger" else action
    url = f"{HA_URL}/api/services/{domain}/{service}"

    try:
        r = requests.post(url, headers=headers, json={"entity_id": entity_id}, timeout=10)
        return r.status_code in (200, 201)
    except Exception as e:
        logger.error(f"[HA] Fehler beim Service Call: {e}")
        return False


def get_state(entity_id: str) -> dict | None:
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{HA_URL}/api/states/{entity_id}"

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"[HA] get_state '{entity_id}' Status {r.status_code}")
        return None
    except Exception as e:
        logger.error(f"[HA] Fehler beim State Fetch: {e}")
        return None
