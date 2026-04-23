import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.ha import trigger_automation
from bot.menu import get_main_menu_keyboard, send_main_menu, save_bot_message, delete_last_bot_message
from bot.battery import check_battery

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, context)
    logger.info(f"Start from user {update.effective_user.id}")


async def show_tor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚶 Tor Geh", callback_data="tor_geh")],
        [InlineKeyboardButton("🔒 Tor Geh Fix", callback_data="tor_geh_fix")],
        [InlineKeyboardButton("🚗 Tor Auto", callback_data="tor_auto")],
        [InlineKeyboardButton("🔧 Tor Auto Fix", callback_data="tor_auto_fix")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="zurueck_hauptmenue")],
    ]
    msg = await update.message.reply_text(
        "🚪 TOR-Optionen wählen:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await save_bot_message(context, msg)


async def show_pool_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💧 Pump ON", callback_data="pool_pump_on")],
        [InlineKeyboardButton("💧 Pump OFF", callback_data="pool_pump_off")],
        [InlineKeyboardButton("🔥 Heat Pool", callback_data="pool_heat_on")],
        [InlineKeyboardButton("❄️ Heat OFF", callback_data="pool_heat_off")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="zurueck_hauptmenue")],
    ]
    msg = await update.message.reply_text(
        "🏊 Pool-Steuerung:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await save_bot_message(context, msg)


async def handle_main_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await delete_last_bot_message(update, context)

    if text == "🚪 TOR-Steuerung":
        await show_tor_menu(update, context)
    elif text == "🏊 Pool-Steuerung":
        await show_pool_menu(update, context)
    elif text == "🔋 Batterie prüfen":
        await check_battery(update, context)
    else:
        await update.message.reply_text("Bitte nutze die Buttons im Hauptmenü.")


async def zurueck_hauptmenue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    reply_markup = get_main_menu_keyboard()
    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Hauptmenü – wähle eine Option:",
        reply_markup=reply_markup,
    )
    context.user_data["last_bot_msg_id"] = msg.message_id


async def action_tor_geh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_tor_geh")
    await query.edit_message_text("✅ Tor Geh wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_geh_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_tor_geh_fix")
    await query.edit_message_text("✅ Tor Geh Fix wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_tor_auto")
    await query.edit_message_text("✅ Tor Auto wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_auto_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_tor_auto_fix")
    await query.edit_message_text("✅ Tor Auto Fix wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_pump_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_pool_pump_on")
    await query.edit_message_text("✅ Pool-Pumpe EIN")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_pump_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_pool_pump_off")
    await query.edit_message_text("✅ Pool-Pumpe AUS")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_heat_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_pool_heat_pump_on")
    await query.edit_message_text("🔥 Pool-Heizung EIN")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_heat_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_automation("automation.trigger_pool_heat_pump_off")
    await query.edit_message_text("❄️ Pool-Heizung AUS")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def battery_notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "battery_heat_pool":
        trigger_automation("automation.trigger_pool_heat_pump_on")
        await query.edit_message_text("🔥 Pool-Heizung wurde eingeschaltet.")
    elif query.data == "battery_ignore":
        await query.edit_message_text("Benachrichtigung ignoriert.")

    context.user_data["last_bot_msg_id"] = query.message.message_id
