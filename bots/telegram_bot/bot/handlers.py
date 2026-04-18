from bot.voice import ensure_voice_dir, transcribe_audio
from bot.config import VOICE_REPLY_WITH_TRANSCRIPT
from bot.llm import parse_command
from bot.ha import call_service


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
    command = parse_command(transcript)

    if not command:
        await update.message.reply_text(
            f"❓ Kein passendes Gerät für: *{transcript}*",
            parse_mode="Markdown"
        )
        return

    entity_id = command["entity_id"]
    action = command["action"]
    domain = command["domain"]

    success = call_service(domain, action, entity_id)

    if success:
        await update.message.reply_text(
            f"✅ *{action}* → `{entity_id}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ Fehler beim Ausführen: `{entity_id}`",
            parse_mode="Markdown"
        )
