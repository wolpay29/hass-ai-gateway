import requests
import yaml
import json
import re
import logging
from pathlib import Path
from core.config import (
    LMSTUDIO_URL, LMSTUDIO_MODEL, LMSTUDIO_TIMEOUT, LMSTUDIO_API_KEY,
    LMSTUDIO_TEMPERATURE, LMSTUDIO_NO_THINK,
    LLM_HISTORY_SIZE, MAX_ACTIONS_PER_COMMAND,
    HISTORY_INCLUDE_ASSISTANT,
    USERCONFIG_DIR,
)

logger = logging.getLogger(__name__)

# Gesprächsverlauf pro chat_id — nur aktiv wenn LLM_HISTORY_SIZE > 0
_history: dict[int, list] = {}


def _extract_json(text: str) -> dict | None:
    """JSON aus dem LLM-Output extrahieren.

    Versucht zuerst normales Matching. Falls die schließende } fehlt (Modell-Bug,
    finish_reason=stop aber unvollständiges JSON), werden fehlende } aufgefüllt.
    """
    # Normalfall: vollständiges {…}
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Repair: { ohne schließendes } — fehlende Klammern auffüllen
    start = text.find('{')
    if start == -1:
        return None
    fragment = text[start:]
    depth = 0
    for ch in fragment:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    if depth > 0:
        repaired = fragment + '}' * depth
        try:
            result = json.loads(repaired)
            logger.warning(f"[LLM] JSON repariert ({depth} fehlende '}}') — Modell hat JSON nicht abgeschlossen")
            return result
        except json.JSONDecodeError:
            pass
    return None


def _lmstudio_headers() -> dict:
    """Standard-Header fuer LM Studio /v1-Calls. Fuegt Bearer-Token an,
    wenn LM Studio Server-Auth aktiv ist (sobald MCP genutzt wird Pflicht)."""
    h = {"Content-Type": "application/json"}
    if LMSTUDIO_API_KEY:
        h["Authorization"] = f"Bearer {LMSTUDIO_API_KEY}"
    return h


def _load_entities() -> list:
    path = USERCONFIG_DIR / "entities.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return (data or {}).get("entities") or []


_prompts_cache: dict | None = None
_memory_cache: dict[str, str] = {}


def _load_prompts() -> dict:
    global _prompts_cache
    if _prompts_cache is None:
        path = Path(__file__).parent / "prompts.yaml"
        _prompts_cache = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _prompts_cache


def _load_memory(name: str) -> str:
    """Liest core/userconfig/<name>_memory.md (z.B. 'pre_llm', 'post_llm') als String.

    Liefert "" wenn Datei fehlt oder nur Kommentare/Whitespace enthaelt.
    HTML-Kommentare <!-- ... --> werden entfernt, damit reine Vorlagen-Files
    nichts an den Prompt anhaengen. Cached nach erstem Lesen.
    """
    if name in _memory_cache:
        return _memory_cache[name]
    path = USERCONFIG_DIR / f"{name}_memory.md"
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
    else:
        cleaned = ""
    _memory_cache[name] = cleaned
    return cleaned


def _build_prompt(key: str, memory: str | None = None, **kwargs) -> str:
    prompts = _load_prompts()
    text = prompts[key].format(**kwargs)
    if memory:
        mem = _load_memory(memory)
        if mem:
            text += "\n\n# Zusaetzliche Hinweise / haeufige Fehler\n" + mem
    if LMSTUDIO_NO_THINK:
        text += "\n\n" + prompts["no_think_suffix"]
    return text


def parse_command(transcript: str, chat_id: int = 0) -> dict | None:
    entities = _load_entities()
    valid_ids = {e["id"] for e in entities}

    entity_list = "\n".join(
        f'- {e["id"]} | keywords: {", ".join(e.get("keywords", []))} | actions: {", ".join(e["actions"])}'
        for e in entities
    )

    system_prompt = _build_prompt("primary_parser", memory="post_llm", entity_list=entity_list)

    logger.info(
        f"[LLM] Transcript: '{transcript}' | Modell: {LMSTUDIO_MODEL} | "
        f"Server: {LMSTUDIO_URL} | History: {LLM_HISTORY_SIZE} | "
        f"MaxActions: {MAX_ACTIONS_PER_COMMAND}"
    )

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

        result = _extract_json(content)
        if result is None:
            logger.error("[LLM] Kein JSON gefunden")
            return None
        logger.info(f"[LLM] Parsed: {result}")

        validated_actions = []
        for act in result.get("actions", []):
            if act.get("action") == "needs_fallback":
                validated_actions.append(act)
                logger.info(f"[LLM] needs_fallback fuer '{act.get('entity_id', '?')}'")
            elif act.get("entity_id") and act["entity_id"] in valid_ids:
                validated_actions.append(act)
            elif act.get("entity_id"):
                logger.warning(f"[LLM] Halluzinierte Entity '{act['entity_id']}' – wird ignoriert")

        if MAX_ACTIONS_PER_COMMAND > 0 and len(validated_actions) > MAX_ACTIONS_PER_COMMAND:
            logger.warning(
                f"[LLM] Zu viele Aktionen ({len(validated_actions)}), "
                f"begrenze auf {MAX_ACTIONS_PER_COMMAND}"
            )
            for i in range(MAX_ACTIONS_PER_COMMAND, len(validated_actions)):
                validated_actions[i]["ignored"] = True

        result["actions"] = validated_actions

        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            if HISTORY_INCLUDE_ASSISTANT:
                history.append({"role": "assistant", "content": content})
            max_entries = LLM_HISTORY_SIZE * (2 if HISTORY_INCLUDE_ASSISTANT else 1)
            if len(history) > max_entries:
                history = history[-max_entries:]
            _history[chat_id] = history
            logger.info(f"[LLM] History fuer chat {chat_id}: {len(history)} Eintraege gespeichert")

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


def get_history_snapshot(chat_id: int) -> list:
    """Return a shallow copy of the stored history before the current turn is added."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0:
        return []
    return list(_history.get(chat_id, []))


def get_recent_user_messages(chat_id: int) -> list[str]:
    """Return all stored user messages from history for this chat (oldest first)."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0:
        return []
    return [m["content"] for m in _history.get(chat_id, []) if m["role"] == "user"]


def get_recent_assistant_replies(chat_id: int) -> list[str]:
    """Return stored assistant context (oldest first)."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0:
        return []
    out: list[str] = []
    for m in _history.get(chat_id, []):
        if m["role"] != "assistant":
            continue
        content = m["content"]
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                reply = (parsed.get("reply") or "").strip()
                if reply:
                    out.append(reply)
            except json.JSONDecodeError:
                pass
            trailing = content[match.end():].strip()
            if trailing:
                out.append(trailing)
        else:
            stripped = content.strip()
            if stripped:
                out.append(stripped)
    return out


def append_execution_summary(chat_id: int, summary: str) -> None:
    """Append an execution-summary line to the most recent assistant entry in history."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0 or not summary:
        return
    history = _history.get(chat_id)
    if not history:
        return
    for msg in reversed(history):
        if msg["role"] == "assistant":
            msg["content"] = msg["content"].rstrip() + "\n" + summary
            return


def append_clarification_turn(chat_id: int, transcript: str, question: str) -> None:
    """Persist a clarification round-trip in history."""
    if LLM_HISTORY_SIZE <= 0 or chat_id == 0 or not transcript:
        return
    history = _history.get(chat_id, [])
    history.append({"role": "user", "content": transcript})
    if HISTORY_INCLUDE_ASSISTANT and question:
        history.append({"role": "assistant", "content": question})
    max_entries = LLM_HISTORY_SIZE * (2 if HISTORY_INCLUDE_ASSISTANT else 1)
    if len(history) > max_entries:
        history = history[-max_entries:]
    _history[chat_id] = history
    logger.info(f"[LLM] Clarification-Turn fuer chat {chat_id} gespeichert ({len(history)} Eintraege)")


def smalltalk_reply(transcript: str, chat_id: int = 0) -> dict | None:
    """Free-form chat reply for non-command intents (smalltalk / clarification).

    Returns {"reply": str, "actions": []} — same shape as other parser functions
    so callers can treat all LLM results uniformly. The model may return either
    plain text or JSON; both are handled via _extract_json with a plain-text
    fallback so TTS never receives raw JSON syntax.
    Returns None on error.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        return None

    system_prompt = _build_prompt("smalltalk")

    history = []
    if LLM_HISTORY_SIZE > 0 and chat_id != 0:
        history = _history.get(chat_id, [])

    logger.info(
        f"[LLM Smalltalk] Transcript: '{transcript}' | Modell: {LMSTUDIO_MODEL} | "
        f"History: {len(history) // 2}"
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
        response = requests.post(
            endpoint, json=payload, headers=_lmstudio_headers(), timeout=LMSTUDIO_TIMEOUT
        )
        response.raise_for_status()
        raw = (response.json()["choices"][0]["message"]["content"] or "").strip()

        # Try to parse as JSON first (model often returns {"reply":...,"actions":[]})
        parsed = _extract_json(raw)
        if parsed is not None:
            reply = (parsed.get("reply") or "").strip()
            result = {"reply": reply, "actions": []}
        else:
            # Plain text response — strip stray quotes / labels
            text = raw.strip('"').strip("'")
            text = re.sub(r"^(Assistent|Assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
            result = {"reply": text.strip(), "actions": []}

        if not result["reply"]:
            logger.warning("[LLM Smalltalk] Leere Antwort")
            return None

        logger.info(f"[LLM Smalltalk] Antwort: {result['reply']}")

        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            if HISTORY_INCLUDE_ASSISTANT:
                history.append({"role": "assistant", "content": raw})
            max_entries = LLM_HISTORY_SIZE * (2 if HISTORY_INCLUDE_ASSISTANT else 1)
            if len(history) > max_entries:
                history = history[-max_entries:]
            _history[chat_id] = history

        return result

    except Exception as e:
        logger.error(f"[LLM Smalltalk] Fehler: {e}")
        return None


_RELEVANT_ATTRS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "climate": ("current_temperature", "temperature", "hvac_mode", "hvac_action", "preset_mode", "humidity", "current_humidity", "fan_mode"),
    "cover":   ("current_position", "current_tilt_position"),
    "light":   ("brightness", "color_temp", "color_mode", "rgb_color"),
    "fan":     ("percentage", "preset_mode"),
    "media_player": ("media_title", "media_artist", "volume_level", "source"),
    "weather": ("temperature", "humidity", "wind_speed"),
}


def _humanize_state(domain: str, state: str | None) -> str:
    if state is None:
        return "unbekannt"
    if domain in ("light", "switch", "automation", "input_boolean", "fan", "media_player"):
        if state == "on":
            return "an"
        if state == "off":
            return "aus"
    if domain == "binary_sensor":
        if state == "on":
            return "aktiv"
        if state == "off":
            return "inaktiv"
    return str(state)


def _format_entity_with_state(e: dict, ha_state: dict | None) -> str:
    """Eine Entity-Zeile fuer den RAG-Prompt — mit aktuellem state und relevanten Attributen."""
    eid = e["entity_id"]
    domain = e.get("domain") or (eid.split(".", 1)[0] if "." in eid else "")
    name = e.get("friendly_name") or "-"

    if ha_state is None:
        state_str = "unbekannt"
        attrs_str = ""
    else:
        raw_state = ha_state.get("state")
        attrs = ha_state.get("attributes", {}) or {}
        unit = attrs.get("unit_of_measurement") or ""
        human = _humanize_state(domain, raw_state)
        state_str = f"{human} {unit}".strip() if unit and human not in ("an", "aus", "aktiv", "inaktiv", "unbekannt") else human

        relevant = _RELEVANT_ATTRS_BY_DOMAIN.get(domain, ())
        parts = []
        for k in relevant:
            v = attrs.get(k)
            if v is None or v == "":
                continue
            parts.append(f"{k}={v}")
        attrs_str = (" | " + ", ".join(parts)) if parts else ""

    line = (
        f'- {eid} | name: {name} | state: {state_str}{attrs_str} | '
        f'actions: {", ".join(e.get("actions", [])) or "-"}'
    )
    if e.get("meta"):
        line += f' | note: {e["meta"]}'
    return line


def parse_command_rag(transcript: str, entities: list[dict], chat_id: int = 0) -> dict | None:
    """RAG path: entity list mit aktuellen States, Attributen und expliziten actions."""
    if not entities:
        logger.warning("[LLM RAG] Keine RAG-Entities uebergeben")
        return None

    valid_ids = {e["entity_id"] for e in entities}

    from core.ha import get_states_bulk
    states_map = get_states_bulk(list(valid_ids))
    logger.info(f"[LLM RAG] States geholt: {len(states_map)}/{len(valid_ids)}")

    entity_list = "\n".join(_format_entity_with_state(e, states_map.get(e["entity_id"])) for e in entities)

    system_prompt = _build_prompt("rag_parser", memory="post_llm", entity_list=entity_list)

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

        result = _extract_json(content)
        if result is None:
            logger.error("[LLM RAG] Kein JSON gefunden")
            return None

        clarification_q = (result.get("clarification_question") or "").strip()
        if clarification_q:
            logger.info(f"[LLM RAG] Clarification vom Parser: '{clarification_q}'")
        result["clarification_question"] = clarification_q

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
            sd = act.get("service_data")
            if sd is not None and not isinstance(sd, dict):
                logger.warning(f"[LLM RAG] service_data fuer '{eid}' kein Dict — verwerfe")
                act.pop("service_data", None)
            validated.append(act)

        if MAX_ACTIONS_PER_COMMAND > 0 and len(validated) > MAX_ACTIONS_PER_COMMAND:
            logger.warning(
                f"[LLM RAG] Zu viele Aktionen ({len(validated)}), "
                f"begrenze auf {MAX_ACTIONS_PER_COMMAND}"
            )
            for i in range(MAX_ACTIONS_PER_COMMAND, len(validated)):
                validated[i]["ignored"] = True

        result["actions"] = validated

        if LLM_HISTORY_SIZE > 0 and chat_id != 0:
            history.append({"role": "user", "content": transcript})
            if HISTORY_INCLUDE_ASSISTANT:
                history.append({"role": "assistant", "content": content})
            max_entries = LLM_HISTORY_SIZE * (2 if HISTORY_INCLUDE_ASSISTANT else 1)
            if len(history) > max_entries:
                history = history[-max_entries:]
            _history[chat_id] = history
            logger.info(f"[LLM RAG] History fuer chat {chat_id}: {len(history)} Eintraege gespeichert")

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


def parse_command_with_states(transcript: str, states: list[dict], chat_id: int = 0, prior_history: list | None = None) -> dict | None:
    """REST-Fallback (Mode 1): nutzt Live-Entities aus HA statt entities.yaml."""
    if not states:
        logger.warning("[LLM Fallback REST] Keine Live-States uebergeben")
        return None

    valid_ids = {s["entity_id"] for s in states}

    entity_list = "\n".join(
        f'- {s["entity_id"]} | name: {s.get("friendly_name") or "-"} | '
        f'domain: {s["domain"]} | state: {s.get("state") or "-"}'
        for s in states
    )

    system_prompt = _build_prompt("fallback_rest", memory="post_llm", entity_list=entity_list)

    history = prior_history or []

    logger.info(
        f"[LLM Fallback REST] Transcript: '{transcript}' | Entities: {len(states)} | "
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
        logger.info(f"[LLM Fallback REST] Antwort raw: {content}")

        result = _extract_json(content)
        if result is None:
            logger.error("[LLM Fallback REST] Kein JSON gefunden")
            return None

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
            if not act.get("domain") and "." in eid:
                act["domain"] = eid.split(".", 1)[0]
            sd = act.get("service_data")
            if sd is not None and not isinstance(sd, dict):
                logger.warning(f"[LLM Fallback REST] service_data fuer '{eid}' kein Dict — verwerfe")
                act.pop("service_data", None)
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
