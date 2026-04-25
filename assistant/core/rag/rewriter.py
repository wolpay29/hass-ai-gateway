"""
core.rag.rewriter — pre-RAG query normalization + intent classification.

Runs a small LLM call BEFORE the embedding step to:
  - classify intent (command | smalltalk | clarification)
  - fix typos and STT errors ("lciht" -> "licht")
  - resolve pronouns / follow-ups from recent history ("und wieder aus")
  - preserve the original meaning — never invent entities or actions

Returns a dict {"intent": str, "query": str}. On any error or empty output,
returns {"intent": "command", "query": <original transcript>} so the pipeline
never breaks (commands are the safe default — they go through the normal RAG
+ parser path).
"""
import json
import logging
import re

import requests
import yaml
from pathlib import Path

from core.config import (
    RAG_QUERY_REWRITE,
    RAG_REWRITE_LLM_URL,
    RAG_REWRITE_LLM_API_KEY,
    RAG_REWRITE_MODEL,
    RAG_REWRITE_TIMEOUT,
    RAG_REWRITE_TEMPERATURE,
    HISTORY_INCLUDE_ASSISTANT,
    LMSTUDIO_NO_THINK,
)
from core.llm import get_recent_user_messages, get_recent_assistant_replies

logger = logging.getLogger(__name__)

_VALID_INTENTS = {"command", "smalltalk", "clarification"}

_prompts_cache: dict | None = None


def _load_prompts() -> dict:
    global _prompts_cache
    if _prompts_cache is None:
        path = Path(__file__).parent.parent / "prompts.yaml"
        _prompts_cache = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _prompts_cache


def _build_history_block(chat_id: int) -> str:
    if chat_id == 0:
        return "(leer)"

    lines: list[str] = []
    user_msgs = get_recent_user_messages(chat_id)
    assistant_msgs = (
        get_recent_assistant_replies(chat_id) if HISTORY_INCLUDE_ASSISTANT else []
    )
    for u in user_msgs:
        lines.append(f"Nutzer: {u}")
    for a in assistant_msgs:
        lines.append(f"Assistent: {a}")

    return "\n".join(lines) if lines else "(leer)"


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if RAG_REWRITE_LLM_API_KEY:
        h["Authorization"] = f"Bearer {RAG_REWRITE_LLM_API_KEY}"
    return h


def _safe_default(transcript: str) -> dict:
    return {"intent": "command", "query": transcript}


def rewrite_query(transcript: str, chat_id: int = 0) -> dict:
    """Classify intent and normalize the query for RAG.

    Returns {"intent": "command|smalltalk|clarification", "query": str}.
    Falls back to {"intent": "command", "query": <original>} on any error.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        return _safe_default(transcript)

    if not RAG_QUERY_REWRITE:
        return _safe_default(transcript)

    try:
        prompts = _load_prompts()
        system_prompt = prompts["query_rewriter"].format(
            history=_build_history_block(chat_id),
            transcript=transcript,
        )
        if LMSTUDIO_NO_THINK and "no_think_suffix" in prompts:
            system_prompt += "\n\n" + prompts["no_think_suffix"]

        endpoint = f"{RAG_REWRITE_LLM_URL}/v1/chat/completions"
        payload = {
            "model": RAG_REWRITE_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            "temperature": RAG_REWRITE_TEMPERATURE,
        }

        response = requests.post(
            endpoint, json=payload, headers=_headers(), timeout=RAG_REWRITE_TIMEOUT
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or ""

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            logger.warning(f"[Rewriter] Kein JSON in Antwort: {content!r}")
            return _safe_default(transcript)

        parsed = json.loads(match.group())
        intent = (parsed.get("intent") or "").strip().lower()
        query = (parsed.get("query") or "").strip()

        if intent not in _VALID_INTENTS:
            logger.warning(f"[Rewriter] Unbekannter intent {intent!r} — fallback command")
            intent = "command"

        if not query:
            query = transcript

        logger.info(f"[Rewriter] '{transcript}' -> intent={intent} | query='{query}'")
        return {"intent": intent, "query": query}

    except Exception as e:
        logger.error(f"[Rewriter] Fehler ({e}) — fallback command + Originaltranskript")
        return _safe_default(transcript)
