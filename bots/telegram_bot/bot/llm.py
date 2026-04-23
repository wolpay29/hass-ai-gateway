import requests
import yaml
import json
import re
import logging
from pathlib import Path
from bot.config import (
    LMSTUDIO_URL, LMSTUDIO_MODEL, LMSTUDIO_TIMEOUT, LMSTUDIO_API_KEY,
    LMSTUDIO_TEMPERATURE, LMSTUDIO_NO_THINK,
    LLM_HISTORY_SIZE, MAX_ACTIONS_PER_COMMAND
)

logger = logging.getLogger(__name__)

# Gesprächsverlauf pro chat_id — nur aktiv wenn LLM_HISTORY_SIZE > 0
_history: dict[int, list] = {}


def _lmstudio_headers() -> dict:
    """Standard-Header fuer LM Studio /v1-Calls. Fuegt Bearer-Token an,
    wenn LM Studio Server-Auth aktiv ist (sobald MCP genutzt wird Pflicht)."""
    h = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        h["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"
    return h


def _load_entities() -> list:
    path = Path(__file__).parent / "entities.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return (data or {}).get("entities") or []


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

Format IMMER so (auch bei nur einem Gerät):
{{"reply":"...", "actions":[{{"entity_id":"...","action":"...","domain":"..."}}]}}

Mehrere Geräte gleichzeitig möglich:
{{"reply":"...", "actions":[{{"entity_id":"light.licht_paul","action":"turn_on","domain":"light"}},{{"entity_id":"light.licht_max","action":"turn_on","domain":"light"}}]}}

Kein Treffer:
{{"reply":"...", "actions":[]}}

Aktionen:
- "turn_on" / "turn_off" / "toggle": Gerät steuern (Licht, Schalter)
- "trigger": Automation ausloesen (Tor, Pool Pumpe)
- "get_state": Aktuellen Zustand eines Sensors/Geraets abfragen (z.B. "wie warm ist der Pool?", "ist das Licht bei Paul an?", "wie viel erzeugt die PV?")
- "needs_fallback": Wenn der Nutzer eine Aktion mit Parametern verlangt die hier nicht ausfuehrbar ist (z.B. Temperatur setzen, Helligkeit, Position, Modus). Auch wenn der Nutzer nach einem Wert fragt, den der Entity-Typ nicht liefern kann — z.B. Position/Stellung einer Rollo die als Switch (on/off) definiert ist. Entity-ID trotzdem angeben.

Wenn der Nutzer nach einem Wert, Zustand oder Status fragt, nutze "get_state".
Wenn der Nutzer nach Position/Stellung/Prozent einer Rollo/eines Covers fragt und die Entity ein Switch ist (kein cover-Domain), nutze "needs_fallback".
Bei "get_state" ist "reply" egal — er wird spaeter mit Live-Daten ersetzt. Einfach "..." oder kurzen Platzhalter setzen.

WICHTIG: entity_id MUSS exakt aus der obigen Geräteliste stammen. Niemals eine entity_id erfinden!
"reply" ist immer eine kurze freundliche Antwort auf Deutsch."""

    if LMSTUDIO_NO_THINK:
        system_prompt += "\n\nWICHTIG: Antworte SOFORT und DIREKT. Verwende KEINE <think> Tags und führe keine Gedankengänge aus!"

    logger.info(
        f"[LLM] Transcript: '{transcript}' | Modell: {LMSTUDIO_MODEL} | "
        f"Server: {LMSTUDIO_URL} | History: {LLM_HISTORY_SIZE} | "
        f"MaxActions: {MAX_ACTIONS_PER_COMMAND}"
    )

    # History aufbauen (nur wenn aktiviert)
    history = []
    if LLM_HISTORY_SIZE > 0 and chat_id != 0:
        history = _history.get(chat_id, [])

    try:
        endpoint = f"{LMSTUDIO_URL}/v1/chat/completions"

        payload = {
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": transcript}
            ],
            "temperature": LMSTUDIO_TEMPERATURE
        }

        response = requests.post(endpoint, json=payload, headers=_lmstudio_headers(), timeout=LMSTUDIO_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.info(f"[LLM] Antwort raw: {content}")

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            logger.error("[LLM] Kein JSON gefunden")
            return None

        result = json.loads(match.group())
        logger.info(f"[LLM] Parsed: {result}")

        # Alle entity_ids gegen entities.yaml validieren.
        # "needs_fallback" ist ein Steuersignal, kein echter HA-Aufruf — immer durchlassen.
        validated_actions = []
        for act in result.get("actions", []):
            if act.get("action") == "needs_fallback":
                validated_actions.append(act)
                logger.info(f"[LLM] needs_fallback fuer '{act.get('entity_id', '?')}'")
            elif act.get("entity_id") and act["entity_id"] in valid_ids:
                validated_actions.append(act)
            elif act.get("entity_id"):
                logger.warning(f"[LLM] Halluzinierte Entity '{act['entity_id']}' – wird ignoriert")

        # Limit anwenden und ignorierte Actions markieren
        if MAX_ACTIONS_PER_COMMAND > 0 and len(validated_actions) > MAX_ACTIONS_PER_COMMAND:
            logger.warning(
                f"[LLM] Zu viele Aktionen ({len(validated_actions)}), "
                f"begrenze auf {MAX_ACTIONS_PER_COMMAND}"
            )
            
            # Die ersten N bleiben normal, der Rest bekommt "ignored": True
            for i in range(MAX_ACTIONS_PER_COMMAND, len(validated_actions)):
                validated_actions[i]["ignored"] = True

        result["actions"] = validated_actions

        # History speichern (nur wenn aktiviert)
        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            history.append({"role": "assistant", "content": content})
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


def get_recent_user_messages(chat_id: int) -> list[str]:
    """Return all stored user messages from history for this chat (oldest first)."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0:
        return []
    return [m["content"] for m in _history.get(chat_id, []) if m["role"] == "user"]


def parse_command_rag(transcript: str, entities: list[dict], chat_id: int = 0) -> dict | None:
    """RAG path: entity list with explicit per-entity actions and optional meta hints.

    Expected shape of each dict in `entities`:
        {entity_id, friendly_name, domain, actions: list[str], meta: str}

    Unlike parse_command_with_states() this prompt does NOT describe
    domain-to-action rules generically — each entity lists its own valid
    actions directly. Only `needs_fallback` is explained here, because it
    is a control signal rather than a real HA action and is always available.
    """
    if not entities:
        logger.warning("[LLM RAG] Keine RAG-Entities uebergeben")
        return None

    valid_ids = {e["entity_id"] for e in entities}

    def _fmt(e: dict) -> str:
        line = (
            f'- {e["entity_id"]} | name: {e.get("friendly_name") or "-"} | '
            f'actions: {", ".join(e.get("actions", [])) or "-"}'
        )
        if e.get("meta"):
            line += f' | note: {e["meta"]}'
        return line

    entity_list = "\n".join(_fmt(e) for e in entities)

    system_prompt = f"""Smart Home Assistent. Antworte NUR mit JSON, kein anderer Text.
Du erhaeltst eine vorgefilterte Liste relevanter Home Assistant Entities.
Jede Entity hat ihre erlaubten Aktionen bereits im Feld "actions" aufgelistet —
waehle NUR aus diesen Aktionen.

Geraete:
{entity_list}

Format IMMER so:
{{"reply":"...", "actions":[{{"entity_id":"...","action":"...","domain":"..."}}]}}

Kein Treffer:
{{"reply":"...", "actions":[]}}

Spezialfall "needs_fallback":
Wenn der Nutzer eine Aktion mit Parametern verlangt, die nicht direkt ausfuehrbar
ist (Temperatur setzen, Helligkeit, Rollo-Position, Modus, Prozent-Abfragen auf
Switch-Entities, ...), gib action: "needs_fallback" zurueck. Das gilt auch wenn
die Parameter-Aktion nicht in der actions-Liste der Entity steht — needs_fallback
ist immer erlaubt.

WICHTIG:
- entity_id MUSS exakt aus der obigen Liste stammen. Niemals erfinden.
- "action" MUSS entweder in der actions-Liste der gewaehlten Entity stehen
  ODER "needs_fallback" sein.
- Beachte das optionale "note"-Feld einer Entity als zusaetzlichen Hinweis.
- "domain" ist der Teil vor dem Punkt der entity_id.
- "reply" ist eine kurze freundliche Antwort auf Deutsch.
"""

    if LMSTUDIO_NO_THINK:
        system_prompt += "\n\nWICHTIG: Antworte SOFORT und DIREKT. Verwende KEINE <think> Tags!"

    # History aufbauen (gleiche Logik wie parse_command)
    history = []
    if LLM_HISTORY_SIZE > 0 and chat_id != 0:
        history = _history.get(chat_id, [])

    logger.info(
        f"[LLM RAG] Transcript: '{transcript}' | Entities: {len(entities)} | "
        f"Modell: {LMSTUDIO_MODEL} | History: {len(history) // 2}"
    )

    try:
        endpoint = f"{LMSTUDIO_URL}/v1/chat/completions"
        payload = {
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": transcript},
            ],
            "temperature": LMSTUDIO_TEMPERATURE,
        }
        response = requests.post(endpoint, json=payload, headers=_lmstudio_headers(), timeout=LMSTUDIO_TIMEOUT)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        logger.info(f"[LLM RAG] Antwort raw: {content}")

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            logger.error("[LLM RAG] Kein JSON gefunden")
            return None

        result = json.loads(match.group())

        validated: list[dict] = []
        for act in result.get("actions", []):
            eid = act.get("entity_id")
            if act.get("action") == "needs_fallback":
                validated.append(act)
                logger.info(f"[LLM RAG] needs_fallback fuer '{eid or '?'}'")
                continue
            if not eid:
                continue
            if eid not in valid_ids:
                logger.warning(f"[LLM RAG] Halluzinierte Entity '{eid}' – ignoriert")
                continue
            if not act.get("domain") and "." in eid:
                act["domain"] = eid.split(".", 1)[0]
            validated.append(act)

        if MAX_ACTIONS_PER_COMMAND > 0 and len(validated) > MAX_ACTIONS_PER_COMMAND:
            logger.warning(
                f"[LLM RAG] Zu viele Aktionen ({len(validated)}), "
                f"begrenze auf {MAX_ACTIONS_PER_COMMAND}"
            )
            for i in range(MAX_ACTIONS_PER_COMMAND, len(validated)):
                validated[i]["ignored"] = True

        result["actions"] = validated

        # History speichern (gleiche Logik wie parse_command)
        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            history.append({"role": "assistant", "content": content})
            max_entries = LLM_HISTORY_SIZE * 2
            if len(history) > max_entries:
                history = history[-max_entries:]
            _history[chat_id] = history
            logger.info(f"[LLM RAG] History fuer chat {chat_id}: {len(history) // 2} Austausche gespeichert")

        return result

    except requests.exceptions.HTTPError as e:
        logger.error(f"[LLM RAG] HTTP-Fehler: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[LLM RAG] JSON-Parsing fehlgeschlagen: {e}")
        return None
    except Exception as e:
        logger.error(f"[LLM RAG] Fehler: {e}")
        return None


def parse_command_with_states(transcript: str, states: list[dict], chat_id: int = 0) -> dict | None:
    """REST-Fallback (Mode 1): nutzt Live-Entities aus HA statt entities.yaml.

    Gleiches JSON-Output-Format wie parse_command(). entity_list wird aus den
    uebergebenen Live-States gebaut; Validierung gegen deren entity_ids.
    Wenn ein Treffer gefunden wird, ist das Ergebnis im handlers.py genauso
    ausfuehrbar wie das Ergebnis von parse_command().
    """
    if not states:
        logger.warning("[LLM Fallback REST] Keine Live-States uebergeben")
        return None

    valid_ids = {s["entity_id"] for s in states}

    entity_list = "\n".join(
        f'- {s["entity_id"]} | name: {s.get("friendly_name") or "-"} | '
        f'domain: {s["domain"]} | state: {s.get("state") or "-"}'
        for s in states
    )

    system_prompt = f"""Smart Home Assistent. Antworte NUR mit JSON, kein anderer Text.
Du erhaeltst eine Live-Liste aller Home Assistant Entities (kein vordefinierter Katalog).

Geraete (live aus Home Assistant):
{entity_list}

Format IMMER so:
{{"reply":"...", "actions":[{{"entity_id":"...","action":"...","domain":"..."}}]}}

Kein Treffer:
{{"reply":"...", "actions":[]}}

Aktionen:
- "turn_on" / "turn_off" / "toggle" fuer light/switch/cover
- "trigger" fuer automation
- "get_state" fuer Zustandsabfragen (sensor, binary_sensor, climate, ...)
- "needs_fallback": Wenn der Nutzer eine Aktion mit Parametern verlangt die hier nicht ausfuehrbar ist (z.B. Temperatur setzen, Helligkeit, Position, Modus). Auch wenn der Nutzer nach Position/Stellung/Prozent fragt und die Entity ein Switch ist (kein cover-Domain). Entity-ID trotzdem angeben.

WICHTIG: entity_id MUSS exakt aus der obigen Live-Liste stammen. Niemals erfinden!
"domain" ist der Teil vor dem Punkt in der entity_id.
"reply" ist eine kurze freundliche Antwort auf Deutsch."""

    if LMSTUDIO_NO_THINK:
        system_prompt += "\n\nWICHTIG: Antworte SOFORT und DIREKT. Verwende KEINE <think> Tags!"

    logger.info(
        f"[LLM Fallback REST] Transcript: '{transcript}' | Entities: {len(states)} | "
        f"Modell: {LMSTUDIO_MODEL}"
    )

    try:
        endpoint = f"{LMSTUDIO_URL}/v1/chat/completions"
        payload = {
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            "temperature": LMSTUDIO_TEMPERATURE,
        }
        response = requests.post(endpoint, json=payload, headers=_lmstudio_headers(), timeout=LMSTUDIO_TIMEOUT)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        logger.info(f"[LLM Fallback REST] Antwort raw: {content}")

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            logger.error("[LLM Fallback REST] Kein JSON gefunden")
            return None

        result = json.loads(match.group())

        validated: list[dict] = []
        for act in result.get("actions", []):
            eid = act.get("entity_id")
            if act.get("action") == "needs_fallback":
                validated.append(act)
                logger.info(f"[LLM Fallback REST] needs_fallback fuer '{eid or '?'}'")
                continue
            if not eid:
                continue
            if eid not in valid_ids:
                logger.warning(f"[LLM Fallback REST] Halluzinierte Entity '{eid}' - ignoriert")
                continue
            # domain nachziehen falls das Modell sie nicht geliefert hat
            if not act.get("domain") and "." in eid:
                act["domain"] = eid.split(".", 1)[0]
            validated.append(act)

        if MAX_ACTIONS_PER_COMMAND > 0 and len(validated) > MAX_ACTIONS_PER_COMMAND:
            logger.warning(
                f"[LLM Fallback REST] Zu viele Aktionen ({len(validated)}), "
                f"begrenze auf {MAX_ACTIONS_PER_COMMAND}"
            )
            for i in range(MAX_ACTIONS_PER_COMMAND, len(validated)):
                validated[i]["ignored"] = True

        result["actions"] = validated
        return result

    except requests.exceptions.HTTPError as e:
        logger.error(f"[LLM Fallback REST] HTTP-Fehler: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[LLM Fallback REST] JSON-Parsing fehlgeschlagen: {e}")
        return None
    except Exception as e:
        logger.error(f"[LLM Fallback REST] Fehler: {e}")
        return None


def _format_state_simple(state_data: list[dict]) -> str:
    """Programmatischer Fallback falls der zweite LLM-Aufruf fehlschlaegt."""
    parts = []
    for item in state_data:
        ha = item.get("ha_response")
        # Kuratierte Beschreibung aus entities.yaml bevorzugen (ist menschenfreundlicher
        # als der oft technische HA friendly_name wie "SN: 3015651602 PV Power")
        label = item.get("description") or item["entity_id"]
        if ha is None:
            parts.append(f"{label}: nicht verfügbar")
            continue
        state = ha.get("state", "unbekannt")
        attrs = ha.get("attributes", {})
        unit = attrs.get("unit_of_measurement", "")
        # Licht/Schalter/Binary-Sensor lesbar machen
        if state == "on":
            state = "an"
        elif state == "off":
            state = "aus"
        parts.append(f"{label}: {state}{' ' + unit if unit else ''}")
    return "\n".join(parts)


def format_state_reply(transcript: str, state_data: list[dict], chat_id: int = 0) -> str:
    """
    Zweiter LLM-Aufruf: generiert eine natuerliche Antwort basierend auf Live-Zustandsdaten aus HA.
    Faellt bei Fehler auf einfache programmatische Formatierung zurueck.

    state_data: Liste von dicts mit {entity_id, description, ha_response}
    """
    if not state_data:
        return ""

    data_lines = []
    for item in state_data:
        entity_id = item["entity_id"]
        description = item.get("description", "")
        ha = item.get("ha_response")
        if ha is None:
            data_lines.append(f"- {entity_id} ({description}): FEHLER beim Abruf")
            continue
        state = ha.get("state")
        attributes = ha.get("attributes", {})
        unit = attributes.get("unit_of_measurement")
        # Wert bereits mit Einheit zusammensetzen, damit das Modell nichts
        # kombinieren muss — es kopiert einfach den Wert in die Antwort.
        value = f"{state} {unit}" if unit else str(state)
        # Nur relevante Zusatz-Attribute senden (fuer Cover-Position, Climate-Modi etc.)
        relevant_keys = {
            "device_class", "current_position", "hvac_mode",
            "current_temperature", "target_temperature", "humidity",
        }
        filtered_attrs = {k: v for k, v in attributes.items() if k in relevant_keys}
        line = f"- {entity_id} ({description}): value=\"{value}\""
        if filtered_attrs:
            line += f" attributes={json.dumps(filtered_attrs, ensure_ascii=False)}"
        data_lines.append(line)

    data_block = "\n".join(data_lines)

    # WICHTIG: strukturiertes JSON-Output erzwingen — genau wie beim ersten Call.
    # Thinking-Modelle lassen bei offenen Aufgaben manchmal den "content" leer und
    # erledigen alles im reasoning_content. Mit erzwungenem JSON-Format produziert
    # das Modell zuverlaessig Output.
    system_prompt = """Smart Home Assistent. Antworte NUR mit JSON, kein anderer Text.

Du erhaeltst eine Frage und Live-Daten aus Home Assistant. Formuliere eine kurze, natuerliche deutsche Antwort und gib sie als JSON zurueck.

Format IMMER so:
{"antwort":"..."}

Regeln fuer die Antwort:
- "value" ist der fertige Wert inkl. Einheit — einfach uebernehmen, nicht umrechnen
- Bei binary_sensor: "on" = offen/aktiv, "off" = geschlossen/inaktiv
- Bei Lichtern/Schaltern: "on" = an, "off" = aus
- Bei Rollo/Cover: "current_position" aus attributes in Prozent
- Falls gefragte Information nicht in Daten ist, das ehrlich sagen
- Kurzer, direkter deutscher Satz, keine Einleitungen, keine Markdown-Formatierung"""

    user_content = f"Frage: {transcript}\n\nLive-Daten aus Home Assistant:\n{data_block}\n\nAntworte jetzt NUR mit JSON im Format {{\"antwort\":\"...\"}}."

    logger.info(f"[LLM Step2] Transcript: '{transcript}' | Entities: {[i['entity_id'] for i in state_data]}")

    try:
        endpoint = f"{LMSTUDIO_URL}/v1/chat/completions"
        payload = {
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": LMSTUDIO_TEMPERATURE,
        }
        response = requests.post(endpoint, json=payload, headers=_lmstudio_headers(), timeout=LMSTUDIO_TIMEOUT)
        response.raise_for_status()
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        content = msg.get("content") or ""

        logger.info(f"[LLM Step2] Raw: {repr(content)}")

        if not content.strip():
            reasoning_len = len(msg.get("reasoning_content") or "")
            logger.warning(
                f"[LLM Step2] content leer (reasoning_content: {reasoning_len} Zeichen) "
                f"— nutze programmatischen Fallback"
            )

        # JSON aus der Antwort extrahieren (gleiche Technik wie im ersten Call)
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                antwort = (parsed.get("antwort") or "").strip()
                if antwort:
                    logger.info(f"[LLM Step2] Antwort: {antwort}")
                    return antwort
            except json.JSONDecodeError as e:
                logger.warning(f"[LLM Step2] JSON-Parsing fehlgeschlagen: {e}")

    except Exception as e:
        logger.error(f"[LLM Step2] Fehler: {e}")

    # Fallback: einfache programmatische Formatierung
    fallback = _format_state_simple(state_data)
    logger.info(f"[LLM Step2] Fallback verwendet: {fallback}")
    return fallback