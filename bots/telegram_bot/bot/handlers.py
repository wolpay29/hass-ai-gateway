from bot.voice import ensure_voice_dir, transcribe_audio
from bot.config import (
    VOICE_REPLY_WITH_TRANSCRIPT, MAX_ACTIONS_PER_COMMAND,
    FALLBACK_MODE, FALLBACK_REST_DOMAINS, FALLBACK_REST_MAX_ENTITIES,
)
from bot.llm import parse_command, parse_command_with_states, format_state_reply, _load_entities
from bot.llm_lmstudio import fallback_via_mcp
from bot.ha import call_service, get_state, get_all_states


async def _process_command(update, context, transcript: str):
    command = parse_command(transcript, chat_id=update.effective_chat.id)

    if not command:
        await update.message.reply_text("❓ Ich konnte deine Anfrage nicht verarbeiten.")
        return

    reply = command.get("reply", "")
    actions = command.get("actions", [])
    fallback_states: list[dict] = []

    # needs_fallback: Entity gefunden, aber Aktion braucht Parameter (z.B. set_temperature).
    # Mode 1 hat dieselbe 5-Aktionen-Einschraenkung -> direkt zu Mode 2 springen.
    if any(a.get("action") == "needs_fallback" for a in actions):
        if FALLBACK_MODE == 2:
            mcp_reply = fallback_via_mcp(transcript, chat_id=update.effective_chat.id)
            if mcp_reply:
                await update.message.reply_text(mcp_reply)
            else:
                await update.message.reply_text("❓ MCP-Fallback fehlgeschlagen.")
        else:
            await update.message.reply_text(
                "❓ Diese Aktion benötigt Parameter (z.B. Temperatur, Position) "
                "die hier nicht ausführbar sind. Aktiviere FALLBACK_MODE=2 für MCP-Unterstützung."
            )
        return

    if not actions:
        # Kein Treffer in entities.yaml -> je nach FALLBACK_MODE weitermachen
        if FALLBACK_MODE == 1:
            # REST-Fallback: alle HA-Entities holen und LLM mit Live-Liste fragen
            fallback_states = get_all_states(
                FALLBACK_REST_DOMAINS or None,
                FALLBACK_REST_MAX_ENTITIES,
            )
            fb = parse_command_with_states(
                transcript, fallback_states, chat_id=update.effective_chat.id
            )
            if fb and fb.get("actions"):
                command = fb
                reply = command.get("reply", "")
                actions = command.get("actions", [])
            else:
                await update.message.reply_text(
                    "❓ Kein passendes Gerät gefunden (REST-Fallback ohne Treffer)."
                )
                return
        elif FALLBACK_MODE == 2:
            # MCP-Fallback: LM Studio macht alles (Tool-Auswahl, Ausfuehrung, Antwort)
            mcp_reply = fallback_via_mcp(transcript, chat_id=update.effective_chat.id)
            if mcp_reply:
                await update.message.reply_text(mcp_reply)
            else:
                await update.message.reply_text("❓ MCP-Fallback fehlgeschlagen.")
            return
        else:
            await update.message.reply_text(
                f"💬 {reply}" if reply else "❓ Kein passendes Gerät gefunden."
            )
            return

    entities_by_id = {e["id"]: e for e in _load_entities()}
    # Fuer REST-Fallback: Live-States als Beschreibungsquelle (friendly_name)
    states_by_id = {s["entity_id"]: s for s in fallback_states}

    executed_results = []
    ignored_results = []
    state_queries = []  # {entity_id, description, ha_response}

    for act in actions:
        entity_id = act.get("entity_id")
        action = act.get("action")
        domain = act.get("domain")

        # Wurde die Action vom Limit in llm.py abgeschnitten?
        if act.get("ignored"):
            ignored_results.append(f"❌ `{action}` -> `{entity_id}`")
            continue

        # Sicherheitshalber nochmal das harte Limit prüfen
        # (executed_results enthaelt bereits sowohl Steuer- als auch get_state-Actions)
        if MAX_ACTIONS_PER_COMMAND > 0 and len(executed_results) >= MAX_ACTIONS_PER_COMMAND:
            ignored_results.append(f"❌ `{action}` -> `{entity_id}`")
            continue

        if action == "get_state":
            ha_response = get_state(entity_id)
            # Beschreibung bevorzugt aus entities.yaml; fuer REST-Fallback-Entities
            # friendly_name aus den Live-States als Ersatz.
            description = (
                entities_by_id.get(entity_id, {}).get("description")
                or states_by_id.get(entity_id, {}).get("friendly_name", "")
            )
            state_queries.append({
                "entity_id": entity_id,
                "description": description,
                "ha_response": ha_response,
            })
            icon = "✅" if ha_response else "❌"
            executed_results.append(f"{icon} `get_state` -> `{entity_id}`")
        else:
            success = call_service(domain, action, entity_id)
            icon = "✅" if success else "❌"
            executed_results.append(f"{icon} `{action}` -> `{entity_id}`")

    # Falls Zustandsabfragen dabei waren: zweiter LLM-Aufruf fuer natuerliche Antwort
    final_reply = reply
    if state_queries:
        final_reply = format_state_reply(transcript, state_queries, chat_id=update.effective_chat.id)

    # Nachricht zusammenbauen
    answer = f"{final_reply}\n\n" if final_reply else ""

    if executed_results:
        answer += "\n".join(executed_results)

    if ignored_results:
        answer += f"\n\n⚠️ *Durch Limit ({MAX_ACTIONS_PER_COMMAND}) ignoriert:*\n"
        answer += "\n".join(ignored_results)

    try:
        await update.message.reply_text(answer, parse_mode="Markdown")
    except Exception as e:
        # Falls die Antwort kaputte Markdown enthaelt (z.B. von einem Modell erzeugt),
        # ohne Parse-Modus erneut senden damit die Nachricht nicht ganz verloren geht.
        await update.message.reply_text(answer)


async def handle_voice(update, context):
    if not update.message or not update.message.voice:
        return

    voice_dir = ensure_voice_dir()
    telegram_file = await context.bot.get_file(update.message.voice.file_id)
    file_name = f"{update.message.voice.file_unique_id}.ogg"
    file_path = voice_dir / file_name
    await telegram_file.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text("🎙️ Transkribiere...")
    transcript = transcribe_audio(str(file_path))

    if not transcript:
        await update.message.reply_text("❌ Sprachnachricht nicht verstanden.")
        return

    if VOICE_REPLY_WITH_TRANSCRIPT:
        await update.message.reply_text(f"📝 Erkannt: {transcript}")

    await update.message.reply_text("🤖 Analysiere Befehl...")
    await _process_command(update, context, transcript)


async def handle_text(update, context):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    await update.message.reply_text("🤖 Analysiere...")
    await _process_command(update, context, text)