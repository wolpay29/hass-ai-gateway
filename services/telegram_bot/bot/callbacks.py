import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.ha import trigger_automation, call_service, get_ha_state
from core.strings import t
from bot.menu import get_main_menu_keyboard, send_main_menu, save_bot_message, delete_last_bot_message
from bot import menu_config

logger = logging.getLogger(__name__)


def _resolve_title(title: str) -> str:
    for entity_id in re.findall(r'\{([^}]+)\}', title):
        value = get_ha_state(entity_id) or "?"
        title = title.replace(f"{{{entity_id}}}", value)
    return title


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, context)
    logger.info(f"Start from user {update.effective_user.id}")


async def _show_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str):
    menu = menu_config.get_menu(label)
    title = _resolve_title(menu["title"])
    keyboard = [
        [InlineKeyboardButton(btn["label"], callback_data=btn["callback_data"]) for btn in row]
        for row in menu["rows"]
    ]
    keyboard.append([InlineKeyboardButton(t("back_button"), callback_data="zurueck_hauptmenue")])
    msg = await update.message.reply_text(title, reply_markup=InlineKeyboardMarkup(keyboard))
    await save_bot_message(context, msg)


async def handle_main_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = update.message.text
    await delete_last_bot_message(update, context)

    menu = menu_config.get_menu(label)
    if menu is None:
        await update.message.reply_text(t("use_menu_buttons"))
        return

    if "rows" in menu:
        await _show_submenu(update, context, label)


async def zurueck_hauptmenue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=t("main_menu_header"),
        reply_markup=get_main_menu_keyboard(),
    )
    context.user_data["last_bot_msg_id"] = msg.message_id


async def action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    btn = menu_config.get_all_action_buttons().get(query.data)
    if btn is None:
        await query.edit_message_text(t("unknown_action"))
        return

    if "automation" in btn:
        trigger_automation(btn["automation"])
    elif "service" in btn:
        domain, action = btn["service"].split(".", 1)
        call_service(domain, action, btn["entity_id"])

    await query.edit_message_text(btn.get("response", t("executed")))
    context.user_data["last_bot_msg_id"] = query.message.message_id
