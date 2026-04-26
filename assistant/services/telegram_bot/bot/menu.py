import logging

from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import Application, ContextTypes

from core.config import MY_CHAT_ID

logger = logging.getLogger(__name__)


async def delete_last_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "last_bot_msg_id" not in context.user_data:
        return
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=context.user_data["last_bot_msg_id"],
        )
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")
    finally:
        context.user_data.pop("last_bot_msg_id", None)


async def save_bot_message(context: ContextTypes.DEFAULT_TYPE, message):
    context.user_data["last_bot_msg_id"] = message.message_id


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    from bot.menu_config import get_main_menu_layout
    layout = get_main_menu_layout()
    keyboard = [[KeyboardButton(label) for label in row] for row in layout]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, is_persistent=True)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_startup=False):
    if not is_startup and update.effective_chat:
        await delete_last_bot_message(update, context)

    reply_markup = get_main_menu_keyboard()

    if update.callback_query:
        msg = await update.callback_query.message.reply_text(
            "🏠 Hauptmenü – wähle eine Option:",
            reply_markup=reply_markup,
        )
        try:
            await update.callback_query.answer()
        except Exception:
            pass
    elif update.message:
        msg = await update.message.reply_text(
            "🏠 Hauptmenü – wähle eine Option:",
            reply_markup=reply_markup,
        )
    else:
        return

    await save_bot_message(context, msg)


async def startup_menu(app: Application):
    try:
        reply_markup = get_main_menu_keyboard()
        await app.bot.send_message(
            chat_id=MY_CHAT_ID,
            text="🏠 Bot wurde gestartet – Hauptmenü aktiviert.",
            reply_markup=reply_markup,
        )
        logger.info("Startup menu sent")
    except Exception as e:
        logger.error(f"Error sending startup menu: {e}")
