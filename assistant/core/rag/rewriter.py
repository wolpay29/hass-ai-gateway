"""
core.rag.rewriter — pre-RAG query normalization.

Runs a small LLM call BEFORE the embedding step to:
  - fix typos and STT errors ("lciht" -> "licht")
  - resolve pronouns / follow-ups from recent history ("und wieder aus")
  - preserve the original meaning — never invent entities or actions

The output is a single short German search phrase that gets embedded by the
RAG index. On any error or empty output, the original transcript is returned
so the pipeline never breaks.
"""
import logging
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


def rewrite_query(transcript: str, chat_id: int = 0) -> str:
    """Return a normalized search phrase for the RAG embed step.

    Falls back to the original transcript on any error or empty output.
    """
    if not RAG_QUERY_REWRITE:
        return transcript

    transcript = (transcript or "").strip()
    if not transcript:
        return transcript

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
        content = response.json()["choices"][0]["message"]["content"]

        rewritten = (content or "").strip().strip('"').strip("'")
        # Single line only; LLMs occasionally add explanations on extra lines.
        rewritten = rewritten.splitlines()[0].strip() if rewritten else ""

        if not rewritten:
            logger.warning("[Rewriter] Leere Antwort — verwende Originaltranskript")
            return transcript

        if rewritten.lower() == transcript.lower():
            logger.info(f"[Rewriter] Unveraendert: '{transcript}'")
        else:
            logger.info(f"[Rewriter] '{transcript}' -> '{rewritten}'")
        return rewritten

    except Exception as e:
        logger.error(f"[Rewriter] Fehler ({e}) — verwende Originaltranskript")
        return transcript
