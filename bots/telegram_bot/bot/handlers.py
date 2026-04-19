from bot.voice import ensure_voice_dir, transcribe_audio
from bot.config import VOICE_REPLY_WITH_TRANSCRIPT, MAX_ACTIONS_PER_COMMAND
from bot.llm import parse_command
from bot.ha import call_service


async def _process_command(update, context, transcript: str):
    command = parse_command(transcript, chat_id=update.effective_chat.id)

    if not command:
        await update.message.reply_text("❓ Ich konnte deine Anfrage nicht verarbeiten.")
        return

    reply = command.get("reply", "")
    actions = command.get("actions", [])

    if not actions:
        await update.message.reply_text(f"💬 {reply}" if reply else "❓ Kein passendes Gerät gefunden.")
        return

    executed_results = []
    ignored_results = []

    # Aktionen sortieren und ausführen
    for act in actions:
        entity_id = act.get("entity_id")
        action = act.get("action")
        domain = act.get("domain")
        
        # Wurde die Action vom Limit in llm.py abgeschnitten?
        if act.get("ignored"):
            ignored_results.append(f"❌ `{entity_id}` (`{action}`)")
            continue
            
        # Sicherheitshalber nochmal das harte Limit prüfen
        if MAX_ACTIONS_PER_COMMAND > 0 and len(executed_results) >= MAX_ACTIONS_PER_COMMAND:
            ignored_results.append(f"❌ `{entity_id}` (`{action}`)")
            continue

        # Ausführen
        success = call_service(domain, action, entity_id)
        icon = "✅" if success else "❌"
        executed_results.append(f"{icon} `{action}` → `{entity_id}`")

    # Nachricht zusammenbauen
    answer = f"✅ {reply}\n\n" if reply else ""
    
    if executed_results:
        answer += "\n".join(executed_results)
        
    if ignored_results:
        answer += f"\n\n⚠️ *Durch Limit ({MAX_ACTIONS_PER_COMMAND}) ignoriert:*\n"
        answer += "\n".join(ignored_results)

    await update.message.reply_text(answer, parse_mode="Markdown")


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