import logging

from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import Application, ContextTypes

from core.config import MY_CHAT_ID
from core.strings import t

logger = logging.getLogger(__name__)


async def _delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, key: str):
    msg_id = context.user_data.pop(key, None)
    if not msg_id:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.debug(f"Could not delete message {key}={msg_id}: {e}")


async def delete_submenu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat:
        await _delete_message(context, update.effective_chat.id, "submenu_msg_id")


async def delete_main_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat:
        await _delete_message(context, update.effective_chat.id, "main_menu_msg_id")


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    from bot.menu_config import get_main_menu_layout
    layout = get_main_menu_layout()
    keyboard = [[KeyboardButton(label) for label in row] for row in layout]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, is_persistent=True)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_startup=False):
    """Send a fresh main-menu message carrying the ReplyKeyboard.

    Always sends a new message (rather than editing) so the ReplyKeyboard's
    carrier message is fresh — important when the chat auto-deletes history.
    """
    chat_id = update.effective_chat.id if update.effective_chat else MY_CHAT_ID

    # Replace any previous main-menu carrier so we don't pile up duplicates.
    if not is_startup:
        await delete_submenu_message(update, context)
        await delete_main_menu_message(update, context)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=t("main_menu_header"),
        reply_markup=get_main_menu_keyboard(),
    )
    context.user_data["main_menu_msg_id"] = msg.message_id

    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass


async def startup_menu(app: Application):
    try:
        reply_markup = get_main_menu_keyboard()
        await app.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=t("startup_message"),
            reply_markup=reply_markup,
        )
        logger.info("Startup menu sent")
    except Exception as e:
        logger.error(f"Error sending startup menu: {e}")
