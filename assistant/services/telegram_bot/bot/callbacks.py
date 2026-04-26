import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.ha import trigger_automation
from bot.menu import get_main_menu_keyboard, send_main_menu, save_bot_message, delete_last_bot_message
from bot.battery import check_battery
from bot import menu_config

logger = logging.getLogger(__name__)

_SPECIAL_ACTIONS = {
    "check_battery": check_battery,
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, context)
    logger.info(f"Start from user {update.effective_user.id}")


async def _show_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str):
    menu = menu_config.get_menu(label)
    keyboard = [
        [InlineKeyboardButton(btn["label"], callback_data=btn["callback_data"]) for btn in row]
        for row in menu["rows"]
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Zurück", callback_data="zurueck_hauptmenue")])
    msg = await update.message.reply_text(menu["title"], reply_markup=InlineKeyboardMarkup(keyboard))
    await save_bot_message(context, msg)


async def handle_main_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = update.message.text
    await delete_last_bot_message(update, context)

    menu = menu_config.get_menu(label)
    if menu is None:
        await update.message.reply_text("Bitte nutze die Buttons im Hauptmenü.")
        return

    if "action" in menu:
        action_fn = _SPECIAL_ACTIONS.get(menu["action"])
        if action_fn:
            await action_fn(update, context)
    elif "rows" in menu:
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
        text="🏠 Hauptmenü – wähle eine Option:",
        reply_markup=get_main_menu_keyboard(),
    )
    context.user_data["last_bot_msg_id"] = msg.message_id


async def action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    btn = menu_config.get_all_action_buttons().get(query.data)
    if btn is None:
        await query.edit_message_text("❌ Unbekannte Aktion.")
        return

    if "automation" in btn:
        trigger_automation(btn["automation"])

    await query.edit_message_text(btn.get("response", "✅ Ausgeführt."))
    context.user_data["last_bot_msg_id"] = query.message.message_id
