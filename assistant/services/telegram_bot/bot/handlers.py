"""
Telegram handlers — the Telegram-specific thin layer on top of core.processor.

All command logic (LLM, RAG, HA calls, fallbacks, history) lives in
core.processor. This module only:
  - downloads Telegram voice files,
  - sends intermediate status messages ("🎙️ Transkribiere..."),
  - formats the processor's result dict as Markdown for Telegram.

If you need to change *what* a command does, edit core/processor.py.
If you need to change *how it looks in Telegram*, edit _format_reply() below.
"""
import asyncio
import logging

from core.voice import ensure_voice_dir, transcribe_audio
from core.config import VOICE_REPLY_WITH_TRANSCRIPT, MAX_ACTIONS_PER_COMMAND, RAG_ENABLED
from core.processor import process_transcript

logger = logging.getLogger(__name__)


# Error code → user-visible German message. Keeps all Telegram-facing text in
# one place so translating or rewording is a one-line change.
_ERROR_MESSAGES = {
    "parse_failed":           "❓ Ich konnte deine Anfrage nicht verarbeiten.",
    "fallback_no_match":      "❓ Kein passendes Gerät gefunden (REST-Fallback ohne Treffer).",
    "needs_fallback_no_mode": (
        "❓ Diese Aktion benötigt Parameter (z.B. Temperatur, Position) "
        "die hier nicht ausführbar sind. Aktiviere FALLBACK_MODE=2 für MCP-Unterstützung."
    ),
    "no_match":               "❓ Kein passendes Gerät gefunden.",
    "mcp_failed":             "❓ MCP-Fallback fehlgeschlagen.",
}


def _format_reply(result: dict) -> str:
    """Turn a core.processor result dict into a Markdown Telegram message."""
    error = result.get("error")
    reply = result.get("reply", "")
    executed = result.get("actions_executed", [])
    ignored = result.get("actions_ignored", [])

    # Special case: "no_match" with a reply from the LLM — show the reply
    # (preserves the original "💬 {reply}" behaviour for chatty LLM responses).
    if error == "no_match" and reply:
        return f"💬 {reply}"

    if error and error in _ERROR_MESSAGES:
        return _ERROR_MESSAGES[error]

    parts: list[str] = []
    if reply:
        parts.append(reply)

    if executed:
        parts.append("")  # blank line between reply and action list
        for a in executed:
            icon = "✅" if a["success"] else "❌"
            parts.append(f"{icon} `{a['action']}` -> `{a['entity_id']}`")

    if ignored:
        parts.append("")
        parts.append(f"⚠️ *Durch Limit ({MAX_ACTIONS_PER_COMMAND}) ignoriert:*")
        for a in ignored:
            parts.append(f"❌ `{a['action']}` -> `{a['entity_id']}`")

    text = "\n".join(parts).strip()
    return text or "❓ Kein passendes Gerät gefunden."


async def _dispatch(update, context, transcript: str):
    """Common path: run the processor, format the result, reply to Telegram."""
    result = process_transcript(transcript, chat_id=update.effective_chat.id)
    answer = _format_reply(result)
    try:
        await update.message.reply_text(answer, parse_mode="Markdown")
    except Exception:
        # Fall back to plain-text if the LLM-generated reply contains bad Markdown
        await update.message.reply_text(answer)


async def handle_voice(update, context):
    if not update.message or not update.message.voice:
        return

    voice_dir = ensure_voice_dir()
    telegram_file = await context.bot.get_file(update.message.voice.file_id)
    file_path = voice_dir / f"{update.message.voice.file_unique_id}.ogg"
    await telegram_file.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text("🎙️ Transkribiere...")
    transcript = transcribe_audio(str(file_path))

    if not transcript:
        await update.message.reply_text("❌ Sprachnachricht nicht verstanden.")
        return

    if VOICE_REPLY_WITH_TRANSCRIPT:
        await update.message.reply_text(f"📝 Erkannt: {transcript}")

    await update.message.reply_text("🤖 Analysiere Befehl...")
    await _dispatch(update, context, transcript)


async def handle_text(update, context):
    if not update.message or not update.message.text:
        return

    await update.message.reply_text("🤖 Analysiere...")
    await _dispatch(update, context, update.message.text.strip())


async def handle_rag_rebuild(update, context):
    if not RAG_ENABLED:
        await update.message.reply_text("⚠️ RAG_ENABLED ist nicht aktiv.")
        return

    await update.message.reply_text("🔄 Starte RAG-Index Rebuild ...")
    try:
        from core.rag.index import build as rag_build, status as rag_status

        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, rag_build)
        info = rag_status()
        await update.message.reply_text(
            f"✅ RAG-Index bereit\n"
            f"Entities: {count}\n"
            f"Zuletzt indiziert: {info.get('last_indexed', '?')}"
        )
    except Exception as e:
        logger.error(f"[RAG Rebuild] Fehler: {e}")
        await update.message.reply_text(f"❌ Rebuild fehlgeschlagen: {e}")
