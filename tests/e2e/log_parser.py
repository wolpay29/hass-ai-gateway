"""Parse the voice-gateway subprocess log into per-request structured steps.

Reads the captured log lines (already produced by core/* loggers) for a given
time window and extracts:
  - Whisper transcript
  - Rewriter intent + rewritten query
  - RAG top-K candidates with distances
  - LLM raw + parsed (primary / RAG / REST / smalltalk)
  - HA service-calls (real or DRY-RUN)
  - Processor-level errors / fallback usage

The runner calls extract_steps() with the log lines that were captured between
sending the request and receiving the response. Order is best-effort - we keep
all matches and let the report show them in log order.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


_RE_WHISPER_LOCAL = re.compile(r"\[Whisper LOCAL\] Ergebnis:\s*(.*)$")
_RE_WHISPER_EXT = re.compile(r"\[Whisper EXTERNAL\] Ergebnis:\s*(.*)$")
_RE_REWRITER = re.compile(
    r"\[Rewriter\]\s*'([^']*)'\s*->\s*intent=(\S+)\s*\|\s*query='([^']*)'"
)
_RE_RAG_QUERY = re.compile(
    r"\[RAG Index\] Query '([^']*)'\s*\|\s*(\d+)\s*->\s*(\d+).*?Top-5:\s*(\[.*\])"
)
_RE_RAG_FALLBACK_FILTER = re.compile(
    r"\[RAG Index\] Distance-Filter:\s*(\d+)\s*->\s*(\d+)\s*\(threshold=([\d.]+)\)"
)
_RE_LLM_RAW = re.compile(
    r"\[(LLM RAG|LLM Fallback REST|LLM)\]\s*Antwort raw:\s*(.*)$"
)
_RE_LLM_PARSED = re.compile(
    r"\[(LLM RAG|LLM Fallback REST|LLM)\]\s*Parsed:\s*(.*)$"
)
_RE_LLM_SMALLTALK = re.compile(r"\[LLM Smalltalk\]\s*Antwort:\s*(.*)$")
_RE_HA_DRYRUN = re.compile(r"\[HA DRY-RUN\]\s*([\w.]+)\s+([\w.]+)\s+([\w.]+)(.*)$")
_RE_HA_TIMEOUT = re.compile(r"\[HA\] Timeout bei Service Call\s+([\w.]+)\s+([\w.]+)")
_RE_HA_ERR = re.compile(r"\[HA\] Service-Call\s+([\w.]+)\s+([\w.]+)\s+->\s+(\d+)")
_RE_PROC_FALLBACK = re.compile(r"\[Processor\].*fallback_used.*?(rest|mcp)")


@dataclass
class StepData:
    transcript: str | None = None
    intent: str | None = None
    rewritten_query: str | None = None
    rag_top: list[tuple[str, float]] = field(default_factory=list)
    rag_pre_filter: int | None = None
    rag_post_filter: int | None = None
    rag_threshold: float | None = None
    llm_raw: str | None = None
    llm_parsed: dict | None = None
    llm_path: str | None = None        # "primary" | "rag" | "rest_fallback" | "smalltalk"
    smalltalk_reply: str | None = None
    ha_calls: list[dict] = field(default_factory=list)
    fallback_used_log: str | None = None
    raw_lines: list[str] = field(default_factory=list)


def extract_steps(log_lines: list[str]) -> StepData:
    s = StepData(raw_lines=list(log_lines))
    for line in log_lines:
        if (m := _RE_WHISPER_LOCAL.search(line)) or (m := _RE_WHISPER_EXT.search(line)):
            s.transcript = (m.group(1) or "").strip()
            continue
        if (m := _RE_REWRITER.search(line)):
            s.intent = m.group(2)
            s.rewritten_query = m.group(3)
            continue
        if (m := _RE_RAG_QUERY.search(line)):
            s.rag_pre_filter = int(m.group(2))
            s.rag_post_filter = int(m.group(3))
            s.rag_top = _parse_rag_tuples(m.group(4))
            continue
        if (m := _RE_RAG_FALLBACK_FILTER.search(line)):
            s.rag_pre_filter = int(m.group(1))
            s.rag_post_filter = int(m.group(2))
            s.rag_threshold = float(m.group(3))
            continue
        if (m := _RE_LLM_RAW.search(line)):
            s.llm_raw = m.group(2).strip()
            s.llm_path = _path_from_tag(m.group(1))
            continue
        if (m := _RE_LLM_PARSED.search(line)):
            try:
                # Logged as Python repr - try eval-safe-ish via json fallback
                s.llm_parsed = _safe_parse_dictish(m.group(2).strip())
            except Exception:
                s.llm_parsed = {"_raw": m.group(2).strip()}
            s.llm_path = _path_from_tag(m.group(1))
            continue
        if (m := _RE_LLM_SMALLTALK.search(line)):
            s.smalltalk_reply = m.group(1).strip()
            s.llm_path = "smalltalk"
            continue
        if (m := _RE_HA_DRYRUN.search(line)):
            domain = m.group(1)
            action = m.group(2)
            entity_id = m.group(3)
            s.ha_calls.append({
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "extra": (m.group(4) or "").strip(),
                "dry_run": True,
            })
            continue
        if (m := _RE_HA_ERR.search(line)):
            s.ha_calls.append({
                "service": m.group(1),
                "entity_id": m.group(2),
                "status": m.group(3),
                "dry_run": False,
                "error": True,
            })
            continue
        if (m := _RE_PROC_FALLBACK.search(line)):
            s.fallback_used_log = m.group(1)
    return s


def _path_from_tag(tag: str) -> str:
    if tag == "LLM RAG":
        return "rag"
    if tag == "LLM Fallback REST":
        return "rest_fallback"
    return "primary"


def _parse_rag_tuples(s: str) -> list[tuple[str, float]]:
    """Parse a Python-repr list of tuples like [('light.foo', 0.21), ...]."""
    out: list[tuple[str, float]] = []
    for m in re.finditer(r"\(\s*'([^']+)'\s*,\s*([\d.]+)\s*\)", s):
        try:
            out.append((m.group(1), float(m.group(2))))
        except ValueError:
            pass
    return out


def _safe_parse_dictish(text: str) -> Any:
    """Try JSON first, then a tolerant fallback for Python-repr dicts."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Python repr -> JSON-ish: single quotes -> double, True/False/None -> JSON
    fixed = (
        text.replace("True", "true")
            .replace("False", "false")
            .replace("None", "null")
    )
    # Replace single-quoted strings with double-quoted, but only when they look like keys/values.
    # Conservative regex to avoid mangling apostrophes inside text.
    fixed = re.sub(r"(?<!\\)'", '"', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {"_raw": text}
