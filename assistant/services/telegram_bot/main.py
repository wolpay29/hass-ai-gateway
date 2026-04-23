#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

# Make `core/` importable regardless of where the script is launched from.
# (core/ lives at the project root, two levels up from this file.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from core.config import BOT_TOKEN, CHECK_INTERVAL_SECONDS
from bot.menu import startup_menu
from bot.battery import check_battery, periodic_battery_check
from bot.handlers import handle_voice, handle_text, handle_rag_rebuild
from bot.callbacks import (
    start,
    handle_main_menu_selection,
    zurueck_hauptmenue_callback,
    action_tor_geh,
    action_tor_geh_fix,
    action_tor_auto,
    action_tor_auto_fix,
    action_pool_pump_on,
    action_pool_pump_off,
    action_pool_heat_on,
    action_pool_heat_off,
    battery_notification_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAIN_MENU_PATTERN = r"^(🚪 TOR-Steuerung|🏊 Pool-Steuerung|🔋 Batterie prüfen)$"


def main():
    if not BOT_TOKEN:
        raise ValueError("Missing BOT_TOKEN in .env file")

    app = Application.builder().token(BOT_TOKEN).post_init(startup_menu).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_battery", check_battery))
    app.add_handler(CommandHandler("rag_rebuild", handle_rag_rebuild))

    app.add_handler(MessageHandler(filters.Regex(MAIN_MENU_PATTERN), handle_main_menu_selection))

    app.add_handler(CallbackQueryHandler(zurueck_hauptmenue_callback, pattern=r"^zurueck_hauptmenue$"))
    app.add_handler(CallbackQueryHandler(action_tor_geh, pattern=r"^tor_geh$"))
    app.add_handler(CallbackQueryHandler(action_tor_geh_fix, pattern=r"^tor_geh_fix$"))
    app.add_handler(CallbackQueryHandler(action_tor_auto, pattern=r"^tor_auto$"))
    app.add_handler(CallbackQueryHandler(action_tor_auto_fix, pattern=r"^tor_auto_fix$"))
    app.add_handler(CallbackQueryHandler(action_pool_pump_on, pattern=r"^pool_pump_on$"))
    app.add_handler(CallbackQueryHandler(action_pool_pump_off, pattern=r"^pool_pump_off$"))
    app.add_handler(CallbackQueryHandler(action_pool_heat_on, pattern=r"^pool_heat_on$"))
    app.add_handler(CallbackQueryHandler(action_pool_heat_off, pattern=r"^pool_heat_off$"))
    app.add_handler(CallbackQueryHandler(battery_notification_callback, pattern=r"^(battery_heat_pool|battery_ignore)$"))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(MAIN_MENU_PATTERN),
            handle_text,
        )
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(periodic_battery_check, interval=CHECK_INTERVAL_SECONDS, first=10)
        logger.info(f"Battery check started every {CHECK_INTERVAL_SECONDS} seconds")
    else:
        logger.warning("JobQueue not available. Install python-telegram-bot[job-queue]")

    logger.info("Bot is starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
