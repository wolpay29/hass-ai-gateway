import requests
from bot.config import HA_URL, HA_TOKEN

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
        print(f"[HA] Fehler: {e}")
        return False
