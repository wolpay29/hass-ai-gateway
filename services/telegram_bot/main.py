#!/usr/bin/env python3
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from core.config import BOT_TOKEN
from bot.menu import startup_menu
from bot.handlers import handle_voice, handle_text, handle_rag_rebuild
from bot.callbacks import start, handle_main_menu_selection, zurueck_hauptmenue_callback, action_callback
from bot import menu_config


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    if not BOT_TOKEN:
        raise ValueError("Missing BOT_TOKEN in .env file")

    main_menu_pattern = menu_config.get_main_menu_label_pattern()

    app = Application.builder().token(BOT_TOKEN).post_init(startup_menu).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rag_rebuild", handle_rag_rebuild))

    app.add_handler(MessageHandler(filters.Regex(main_menu_pattern), handle_main_menu_selection))

    app.add_handler(CallbackQueryHandler(zurueck_hauptmenue_callback, pattern=r"^zurueck_hauptmenue$"))

    action_buttons = menu_config.get_all_action_buttons()
    if action_buttons:
        action_pattern = "^(" + "|".join(re.escape(k) for k in action_buttons) + ")$"
        app.add_handler(CallbackQueryHandler(action_callback, pattern=action_pattern))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(main_menu_pattern),
            handle_text,
        )
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logger.info("Bot is starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
