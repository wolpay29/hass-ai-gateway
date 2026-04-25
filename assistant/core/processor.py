"""
core.processor — single source of truth for "transcript in → actions out".

This is the shared brain used by BOTH:
  - bots/telegram_bot  (via handlers.py, which wraps the result in Telegram UI)
  - bots/voice_gateway (via main.py, which returns the result as JSON)

It contains no framework-specific code: no Telegram, no FastAPI, no I/O besides
the LLM/HA calls already encapsulated in core.llm / core.ha.

The function `process_transcript()` returns a plain dict. Callers decide how to
present it (Markdown message, speaker TTS, JSON, etc.).

History
-------
`chat_id` is the history key. Two callers that pass the same `chat_id` see the
same conversation — this lets a Raspberry Pi and your Telegram bot share
history if you set DEVICE_ID on the RPi to your Telegram chat_id (see
bots/voice_gateway/README.md). Different IDs = separate histories.
"""
import logging

from core.config import (
    MAX_ACTIONS_PER_COMMAND,
    FALLBACK_MODE,
    FALLBACK_REST_DOMAINS,
    FALLBACK_REST_MAX_ENTITIES,
    RAG_ENABLED,
    RAG_QUERY_REWRITE,
    RAG_CLARIFY_GAP_THRESHOLD,
    RAG_CLARIFY_SAME_DOMAIN_ONLY,
    HISTORY_INCLUDE_ASSISTANT,
    HISTORY_APPEND_EXECUTIONS,
)
from core.llm import (
    parse_command,
    parse_command_with_states,
    parse_command_rag,
    smalltalk_reply,
    format_state_reply,
    _load_entities,
    get_recent_user_messages,
    get_recent_assistant_replies,
    append_execution_summary,
    append_clarification_turn,
    get_history_snapshot,
)
from core.llm_lmstudio import fallback_via_mcp
from core.ha import call_service, get_state, get_all_states

logger = logging.getLogger(__name__)

# When transcripts are this short, enrich the RAG embed query with history
# context so follow-ups like "und wieder aus" still find the right entity.
_RAG_ENRICH_MAX_WORDS = 5


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------
# process_transcript() returns a dict with this structure:
#
#   {
#     "transcript":       str,            # the input transcript
#     "reply":            str,            # final natural-language reply (may be empty)
#     "actions_executed": [                # actions that were actually sent to HA
#       {"action": "turn_on", "entity_id": "light.paul", "success": True},
#       ...
#     ],
#     "actions_ignored":  [                # actions dropped by MAX_ACTIONS_PER_COMMAND
#       {"action": "turn_on", "entity_id": "light.max"},
#       ...
#     ],
#     "error":            str | None,     # None on success; see ERROR_CODES below
#     "fallback_used":    str | None,     # "rest" | "mcp" | None
#   }
#
# Error codes (all result in actions_executed == [] and typically a user-visible hint):
#   "parse_failed"           — LLM did not return valid JSON
#   "no_match"               — primary + REST path found nothing and MODE!=2
#   "fallback_no_match"      — needs_fallback triggered, REST fallback found nothing
#   "needs_fallback_no_mode" — needs_fallback triggered but FALLBACK_MODE==0
#   "mcp_failed"             — Mode 2 MCP call failed
# ---------------------------------------------------------------------------


def _build_clarification(rag_entities: list[dict]) -> str | None:
    """If the top-1 vs top-2 distance gap is below the configured threshold,
    return a clarification question instead of letting the parser pick blindly.
    Returns None when confident enough or clarification is disabled.
    """
    if len(rag_entities) >= 2:
        top = rag_entities[0]
        second = rag_entities[1]
        d1 = top.get("distance", 0.0) or 0.0
        d2 = second.get("distance", 0.0) or 0.0
        gap = d2 - d1
        logger.info(
            f"[Processor] RAG confidence | top1='{top.get('entity_id')}' "
            f"d1={d1:.4f} | top2='{second.get('entity_id')}' d2={d2:.4f} | "
            f"gap={gap:.4f} | threshold={RAG_CLARIFY_GAP_THRESHOLD} | "
            f"same_domain={top.get('domain') == second.get('domain')}"
        )
    elif rag_entities:
        logger.info(
            f"[Processor] RAG confidence | only 1 candidate "
            f"'{rag_entities[0].get('entity_id')}' "
            f"d={rag_entities[0].get('distance', 0.0):.4f}"
        )

    if RAG_CLARIFY_GAP_THRESHOLD <= 0 or len(rag_entities) < 2:
        return None

    top = rag_entities[0]
    second = rag_entities[1]
    if RAG_CLARIFY_SAME_DOMAIN_ONLY and top.get("domain") != second.get("domain"):
        return None

    gap = (second.get("distance", 0.0) or 0.0) - (top.get("distance", 0.0) or 0.0)
    if gap >= RAG_CLARIFY_GAP_THRESHOLD:
        return None

    name_a = top.get("friendly_name") or top.get("entity_id")
    name_b = second.get("friendly_name") or second.get("entity_id")
    logger.info(
        f"[Processor] Clarification ausgeloest | gap={gap:.4f} < "
        f"{RAG_CLARIFY_GAP_THRESHOLD} | A='{name_a}' B='{name_b}'"
    )
    return f"Meinst du {name_a} oder {name_b}?"


def _resolve_command(transcript: str, embed_query: str, chat_id: int) -> dict | None:
    """Pick the right LLM entry point (RAG or legacy) for the primary path.

    `embed_query` is what gets embedded for RAG retrieval (may be rewritten).
    `transcript` is what the parser LLM sees (original user text).

    RAG errors are caught and logged here, and the function falls back to the
    legacy entities.yaml path so one bad embedding call doesn't kill a command.

    May return a special dict {"_clarify": "<question>"} when RAG retrieval is
    ambiguous — the caller surfaces that as a reply with no actions.
    """
    if RAG_ENABLED:
        try:
            from core.rag.index import query as rag_query

            rag_entities = rag_query(embed_query)
            if rag_entities:
                logger.info(f"[Processor] RAG path | {len(rag_entities)} candidates")
                clarification = _build_clarification(rag_entities)
                if clarification:
                    return {"_clarify": clarification}
                return parse_command_rag(transcript, rag_entities, chat_id=chat_id)
            logger.warning("[Processor] RAG returned no candidates — legacy path")
        except Exception as e:
            logger.error(f"[Processor] RAG failed: {e} — legacy path")

    return parse_command(transcript, chat_id=chat_id)


def _build_embed_query(transcript: str, chat_id: int) -> tuple[str, str]:
    """Return (embed_query, intent). intent is always 'command' when rewriter off."""
    if RAG_QUERY_REWRITE:
        from core.rag.rewriter import rewrite_query
        rw = rewrite_query(transcript, chat_id=chat_id)
        return rw.get("query") or transcript, rw.get("intent") or "command"

    embed_query = transcript
    if len(transcript.split()) <= _RAG_ENRICH_MAX_WORDS:
        context: list[str] = [m for m in get_recent_user_messages(chat_id) if m != transcript]
        if HISTORY_INCLUDE_ASSISTANT:
            context.extend(get_recent_assistant_replies(chat_id))
        if context:
            embed_query = " | ".join(context) + " → " + transcript
            logger.info(f"[Processor] RAG embed query enriched: '{embed_query}'")
    return embed_query, "command"


def _new_result(transcript: str) -> dict:
    return {
        "transcript": transcript,
        "reply": "",
        "actions_executed": [],
        "actions_ignored": [],
        "error": None,
        "fallback_used": None,
    }


def process_transcript(transcript: str, chat_id: int = 0) -> dict:
    """
    transcript → intent → HA actions → result dict.

    chat_id is used both for the history key (see core.llm._history) and for
    logging. Pass 0 to run without history.

    Never raises on LLM/HA errors — those are reported via `result["error"]`.
    """
    result = _new_result(transcript)
    logger.info(
        f"[Processor] chat={chat_id} | FALLBACK_MODE={FALLBACK_MODE} | "
        f"Transcript: '{transcript}'"
    )

    # Snapshot the pre-call history so the REST fallback can use it without
    # seeing the current turn that the primary path is about to append.
    history_snapshot = get_history_snapshot(chat_id)

    # Rewriter (when enabled) classifies intent and produces the embed query.
    embed_query, intent = _build_embed_query(transcript, chat_id)

    if intent in ("smalltalk", "clarification"):
        logger.info(f"[Processor] Intent={intent} — routing to smalltalk LLM")
        chat_reply = smalltalk_reply(transcript, chat_id=chat_id)
        result["reply"] = chat_reply or ""
        if not chat_reply:
            result["error"] = "smalltalk_failed"
        return result

    command = _resolve_command(transcript, embed_query, chat_id)
    if not command:
        result["error"] = "parse_failed"
        return result

    if command.get("_clarify"):
        result["reply"] = command["_clarify"]
        # Originaltranscript + Rueckfrage in die History schreiben, damit der
        # naechste Turn (Antwort auf die Rueckfrage) den urspruenglichen
        # Action-Intent ("abschalten" etc.) noch sieht.
        append_clarification_turn(chat_id, transcript, command["_clarify"])
        return result

    reply = command.get("reply", "")
    actions = command.get("actions", [])
    fallback_states: list[dict] = []

    # -----------------------------------------------------------------------
    # Branch A: needs_fallback — entity matched but action needs parameters
    # (e.g. "set temp to 22", "rollo on 40%") that the curated config can't
    # express. Route to the configured fallback mode.
    # -----------------------------------------------------------------------
    if any(a.get("action") == "needs_fallback" for a in actions):
        if FALLBACK_MODE == 1:
            fallback_states = get_all_states(FALLBACK_REST_DOMAINS or None, FALLBACK_REST_MAX_ENTITIES)
            fb = parse_command_with_states(
                transcript, fallback_states, chat_id=chat_id, prior_history=history_snapshot
            )
            if fb and fb.get("actions") and not any(a.get("action") == "needs_fallback" for a in fb["actions"]):
                command = fb
                reply = command.get("reply", "")
                actions = command.get("actions", [])
                result["fallback_used"] = "rest"
            else:
                result["error"] = "fallback_no_match"
                return result
        elif FALLBACK_MODE == 2:
            mcp_reply = fallback_via_mcp(transcript, chat_id=chat_id)
            if mcp_reply:
                result["reply"] = mcp_reply
                result["fallback_used"] = "mcp"
            else:
                result["error"] = "mcp_failed"
            return result
        else:
            result["error"] = "needs_fallback_no_mode"
            return result

    # -----------------------------------------------------------------------
    # Branch B: no actions at all — primary path found nothing. Try fallbacks.
    # -----------------------------------------------------------------------
    if not actions:
        if FALLBACK_MODE == 1:
            fallback_states = get_all_states(FALLBACK_REST_DOMAINS or None, FALLBACK_REST_MAX_ENTITIES)
            fb = parse_command_with_states(
                transcript, fallback_states, chat_id=chat_id, prior_history=history_snapshot
            )
            if fb and fb.get("actions"):
                command = fb
                reply = command.get("reply", "")
                actions = command.get("actions", [])
                result["fallback_used"] = "rest"
            else:
                result["reply"] = reply
                result["error"] = "no_match"
                return result
        elif FALLBACK_MODE == 2:
            mcp_reply = fallback_via_mcp(transcript, chat_id=chat_id)
            if mcp_reply:
                result["reply"] = mcp_reply
                result["fallback_used"] = "mcp"
            else:
                result["error"] = "mcp_failed"
            return result
        else:
            result["reply"] = reply
            if not reply:
                result["error"] = "no_match"
            return result

    # -----------------------------------------------------------------------
    # Execute HA actions.
    # -----------------------------------------------------------------------
    entities_by_id = {e["id"]: e for e in _load_entities()}
    states_by_id = {s["entity_id"]: s for s in fallback_states}

    state_queries: list[dict] = []  # get_state results for the second LLM pass

    for act in actions:
        entity_id = act.get("entity_id")
        action = act.get("action")
        domain = act.get("domain")

        # Action was dropped by MAX_ACTIONS_PER_COMMAND inside the LLM layer
        if act.get("ignored"):
            result["actions_ignored"].append({"action": action, "entity_id": entity_id})
            continue

        # Safety net: re-check the limit in case the LLM layer didn't apply it
        if MAX_ACTIONS_PER_COMMAND > 0 and len(result["actions_executed"]) >= MAX_ACTIONS_PER_COMMAND:
            result["actions_ignored"].append({"action": action, "entity_id": entity_id})
            continue

        if action == "get_state":
            ha_response = get_state(entity_id)
            description = (
                entities_by_id.get(entity_id, {}).get("description")
                or states_by_id.get(entity_id, {}).get("friendly_name", "")
            )
            state_queries.append({
                "entity_id": entity_id,
                "description": description,
                "ha_response": ha_response,
            })
            result["actions_executed"].append({
                "action": action,
                "entity_id": entity_id,
                "success": ha_response is not None,
            })
        else:
            ok = call_service(domain, action, entity_id)
            result["actions_executed"].append({
                "action": action,
                "entity_id": entity_id,
                "success": ok,
            })

    # Let the LLM see what actually ran so "und wieder aus" follow-ups work
    if HISTORY_APPEND_EXECUTIONS:
        executed = [
            f"{a.get('action')} -> {a.get('entity_id')}"
            for a in actions
            if not a.get("ignored")
            and a.get("action")
            and a.get("entity_id")
            and a.get("action") != "needs_fallback"
        ]
        if executed:
            append_execution_summary(chat_id, "ausgefuehrt: " + ", ".join(executed))

    # If we asked HA for values, second LLM pass formats them as a German sentence
    result["reply"] = format_state_reply(transcript, state_queries, chat_id=chat_id) if state_queries else reply
    return result
