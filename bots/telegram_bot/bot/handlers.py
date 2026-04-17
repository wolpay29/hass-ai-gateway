from bot.voice import ensure_voice_dir, transcribe_audio
from bot.config import VOICE_REPLY_WITH_TRANSCRIPT


async def handle_voice(update, context):
    if not update.message or not update.message.voice:
        return

    voice_dir = ensure_voice_dir()

    telegram_file = await context.bot.get_file(update.message.voice.file_id)

    file_name = f"{update.message.voice.file_unique_id}.ogg"
    file_path = voice_dir / file_name

    await telegram_file.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text("Voice message received. Transcribing...")

    transcript = transcribe_audio(str(file_path))

    if not transcript:
        await update.message.reply_text("I could not understand the voice message.")
        return

    if VOICE_REPLY_WITH_TRANSCRIPT:
        await update.message.reply_text(f"Recognized text:\n\n{transcript}")
