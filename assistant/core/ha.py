import requests
import logging
from core.config import HA_URL, HA_TOKEN

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


def get_all_states(domains: list[str] | None = None, max_entities: int = 0) -> list[dict]:
    """Alle Entity-Zustaende aus HA holen (fuer REST-Fallback Mode 1).

    domains: None oder [] -> kein Filter (alle Domains).
    max_entities: 0 -> kein Limit.
    Rueckgabe: kompakte Liste mit entity_id, state, friendly_name, unit, domain.
    """
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{HA_URL}/api/states"

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            logger.warning(f"[HA] get_all_states Status {r.status_code}")
            return []
        raw = r.json()
    except Exception as e:
        logger.error(f"[HA] Fehler beim get_all_states: {e}")
        return []

    out: list[dict] = []
    for s in raw:
        entity_id = s.get("entity_id", "")
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domains and domain not in domains:
            continue
        attrs = s.get("attributes", {}) or {}
        out.append({
            "entity_id": entity_id,
            "state": s.get("state", ""),
            "friendly_name": attrs.get("friendly_name", ""),
            "unit": attrs.get("unit_of_measurement", ""),
            "domain": domain,
        })
        if max_entities and len(out) >= max_entities:
            break

    logger.info(
        f"[HA] get_all_states: {len(out)} Entities "
        f"(Filter: {domains or 'alle'}, Limit: {max_entities or 'kein'})"
    )
    return out


def get_ha_state(entity_id: str) -> str | None:
    result = get_state(entity_id)
    return result.get("state") if result else None


def trigger_automation(entity_id: str) -> bool:
    return call_service("automation", "trigger", entity_id)


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
